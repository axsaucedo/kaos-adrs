# GPU validation instance — reproducible setup record

This records the disposable single-GPU cloud instance used for the GPU tiers of spikes S3 and S5 (the CUDA-only work: SGLang `--forward-hooks`, vLLM V2 GPU logits and residual patch, CUDA-graph behavior, throughput overhead, CUPTI cost injection, and the GPU semantic-recovery ceiling). It is a runbook, not a standing service: a single box launched, used for one day, and terminated. No cluster orchestration was involved despite the "cluster" label in the plan; one instance was sufficient because tensor/pipeline parallelism was explicitly out of scope for the single-GPU campaign.

The one deferred item that does need more than one GPU — TP/PP rank cardinality, stage-12 assertion #10 — would use the same recipe on a multi-GPU instance type (see the last section).

## What was provisioned

| Item | Value |
|---|---|
| Provider / region | AWS EC2, `eu-central-1` |
| Instance type | `g6.xlarge` — 1× NVIDIA L4 (Ada, 23 GiB), 4 vCPU, 16 GiB RAM |
| AMI | Deep Learning Base AMI with Single CUDA (Ubuntu 24.04), x86_64 |
| Root volume | gp3, `DeleteOnTermination=true` (150 GiB is ample; the campaign over-provisioned to 1000 GiB, which is unnecessary — the AMI plus all spike artifacts used under 20 GiB) |
| Key pair | one EC2 key pair; private key kept locally at `~/.ssh/<key>.pem` |
| Security group | inbound TCP 22 only, from the operator's IP; no other ports needed |
| Login user | `ubuntu` |
| Approximate cost | g6.xlarge on-demand ≈ $0.80–1.00/hr; the campaign ran ~4.5 hours ≈ $4–5 total compute |

## What the AMI provided out of the box

Verified on the running instance — no manual driver or toolkit install was needed:

| Component | Version |
|---|---|
| NVIDIA driver | 595.71.05 |
| CUDA toolkit | 13.2 (at `/usr/local/cuda`), `nvcc` release 13.2 |
| Kernel | `6.17.0-1019-aws`, x86_64 |
| Kernel BTF | present at `/sys/kernel/btf/vmlinux` |
| Docker | 29.6.2 (login user in the `docker` group) |
| Python | 3.12.3 |
| Build tooling | `cmake`, `gcc`, `git` |
| eBPF tooling | `bpftrace` preinstalled |

This AMI choice matters: it is Ubuntu 24.04 with NVIDIA driver plus CUDA preinstalled and **no opinionated ML framework layer**, which keeps the box close to the environment the spikes needed. Ubuntu 24.04 also matches the family S5's CPU tier validated under Colima, and it ships a real kernel with working uprobes and BTF — the S5 hard constraint that Docker Desktop's LinuxKit kernel cannot satisfy. The four-line preflight below is the gate that actually matters; kernel version and BTF presence alone are not sufficient (a uprobe on a real binary must succeed).

## Preflight gate (run immediately after first SSH)

```bash
ssh -i ~/.ssh/<key>.pem ubuntu@<public-dns>
nvidia-smi                    # GPU present, driver/CUDA visible
uname -r                      # real Linux kernel (not *-linuxkit)
ls /sys/kernel/btf/vmlinux    # BTF present, for eBPF CO-RE
id                            # confirm docker group membership
```

For the S5 eBPF work specifically, additionally confirm a real uprobe attaches before trusting the box — the campaign compiled a trivial `noinline` target and asserted 5/5 bpftrace uprobe hits, because BTF visibility alone passed on LinuxKit yet real uprobe attach failed there.

## What ran on it

- **S3 GPU tier** (containerized, official images pinned by digest): SGLang `lmsysorg/sglang:v0.5.16` and vLLM `vllm/vllm-openai:v0.26.0`, both serving `Qwen/Qwen3-0.6B` at a pinned revision. Forward-hook / logits-processor / residual-patch experiments, CUDA-graph matrix, and throughput benchmarks. Docker was used directly (the login user is in the `docker` group); images were pulled quietly and containers stopped after each phase to free the GPU.
- **S5 GPU tier** (built on the host): llama.cpp tag `b10217` compiled `RelWithDebInfo`, unstripped, `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89` (SM89 for the L4). CUPTI injected via `CUDA_INJECTION64_PATH` into the unmodified server; bpftrace uprobes for decode timing and the ggml graph census; `pahole` for struct offsets against the CUDA build.

Work lived under `~/spikes/s3gpu/` and `~/spikes/s5gpu/` on the box. Reports and small JSON evidence were pulled back to the source repo's gitignored `tmp/spikes/`; the box itself held no durable state worth keeping.

## Teardown (do this the moment the campaign ends)

The instance is billed per hour while running, so it must be terminated, not merely stopped, once artifacts are pulled:

```bash
aws ec2 terminate-instances --profile <profile> --region eu-central-1 --instance-ids <instance-id>
aws ec2 wait instance-terminated --profile <profile> --region eu-central-1 --instance-ids <instance-id>
```

`DeleteOnTermination=true` on the root volume means the EBS disk is removed with the instance, so there is no lingering storage cost. In the campaign the instance was terminated the same evening; total lifetime was roughly 4.5 hours.

## Credentials note (security)

The campaign authenticated the AWS CLI with **root-account access keys**, which is against AWS best practice and was flagged for immediate cleanup after teardown. For any repeat: do not use root keys. Prefer **IAM Identity Center (SSO)** — `aws configure sso` then `aws sso login` — which issues short-lived credentials that auto-expire and leave nothing long-lived on disk. If non-interactive access is genuinely required, use a dedicated IAM user with a least-privilege policy scoped to EC2 lifecycle actions (`RunInstances`, `TerminateInstances`, `Describe*`, key-pair and security-group management) constrained to `eu-central-1`, and delete its keys when idle. Never commit any credential to this or any repo.

## Repeating this for the deferred TP/PP item

Stage-12 assertion #10 (rank/worker duplication under tensor/pipeline parallelism) is the only validation item that a single L4 could not close. The same setup applies with two changes: choose a multi-GPU instance type (for example `g6.12xlarge`, 4× L4), and serve with `--tensor-parallel-size 2` (then the intended topology). The test is short — assert that exactly the selected rank emits each logical observation and that no scalar is duplicated across ranks — so a sub-one-hour session suffices. Everything else (AMI, preflight gate, pinned images, teardown, credential posture) is unchanged from this record.
