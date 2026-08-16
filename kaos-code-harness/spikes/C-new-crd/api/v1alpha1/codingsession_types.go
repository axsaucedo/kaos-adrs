// Package v1alpha1 contains spike-C candidate types for design question 2:
// AgentHarness (reusable template) + CodingSession (one run).
//
// The split follows kubernetes-sigs/agent-sandbox's SandboxTemplate/Sandbox shape
// and kagent's AgentHarness naming. Field conventions, marker style, and the
// ContainerOverride/PodSpec escape hatches mirror kaos's own agent_types.go so the
// diff against the real operator is honest.
package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ContainerOverride mirrors kaos's existing ContainerOverride, PLUS the three
// fields spike A found missing for coding workloads. They are reachable today
// only through the full spec.podSpec escape hatch.
type ContainerOverride struct {
	Image     string                      `json:"image,omitempty"`
	Command   []string                    `json:"command,omitempty"`
	Args      []string                    `json:"args,omitempty"`
	Resources corev1.ResourceRequirements `json:"resources,omitempty"`
	Env       []corev1.EnvVar             `json:"env,omitempty"`

	// Added relative to the Agent CRD — see spike A finding 6.
	SecurityContext *corev1.SecurityContext `json:"securityContext,omitempty"`
	WorkingDir      string                  `json:"workingDir,omitempty"`
	VolumeMounts    []corev1.VolumeMount    `json:"volumeMounts,omitempty"`
}

// SecretKeyRef selects a key of a Secret.
type SecretKeyRef struct {
	// +kubebuilder:validation:Required
	Name string `json:"name"`
	// +kubebuilder:validation:Required
	Key string `json:"key"`
}

// RepoSpec describes how the workspace is populated.
type RepoSpec struct {
	// +kubebuilder:validation:Required
	URL string `json:"url"`
	// +kubebuilder:default="main"
	Branch string `json:"branch,omitempty"`
	// +kubebuilder:default=1
	// +kubebuilder:validation:Minimum=0
	Depth int32 `json:"depth,omitempty"`
	// CredentialsRef supplies a token for clone and push.
	CredentialsRef *SecretKeyRef `json:"credentialsRef,omitempty"`
}

// AgentHarnessSpec is the reusable template: which harness, how it authenticates,
// which model and tools it gets. Expensive, stable configuration.
type AgentHarnessSpec struct {
	// Runtime keys into the kaos-harness-runtimes ConfigMap. Left unconstrained
	// (no Enum) deliberately, matching MCPServer.Spec.Runtime — the one
	// data-driven registry pattern in the operator.
	// +kubebuilder:validation:Required
	Runtime string `json:"runtime"`

	// ModelAPI is optional: Claude Code carries its own credential and routes
	// only to Claude models, so a ModelAPI in front of it is a passthrough.
	ModelAPI string `json:"modelAPI,omitempty"`
	Model    string `json:"model,omitempty"`

	// CredentialsRef is the harness's own credential when ModelAPI is unset.
	CredentialsRef *SecretKeyRef `json:"credentialsRef,omitempty"`

	// MCPServers are MCPServer CR names in the same namespace.
	MCPServers []string `json:"mcpServers,omitempty"`

	// RuntimeClassName selects gVisor or Kata for sessions from this template.
	// The Agent CRD never sets this; it is reachable only via spec.podSpec.
	RuntimeClassName *string `json:"runtimeClassName,omitempty"`

	Container *ContainerOverride `json:"container,omitempty"`
	// +kubebuilder:pruning:PreserveUnknownFields
	PodSpec *corev1.PodSpec `json:"podSpec,omitempty"`
}

// AgentHarnessStatus reports template resolvability.
type AgentHarnessStatus struct {
	// +kubebuilder:validation:Enum=Pending;Ready;Failed
	Phase      string             `json:"phase,omitempty"`
	Ready      bool               `json:"ready,omitempty"`
	Image      string             `json:"image,omitempty"`
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=ah
// +kubebuilder:printcolumn:name="Runtime",type=string,JSONPath=`.spec.runtime`
// +kubebuilder:printcolumn:name="Ready",type=boolean,JSONPath=`.status.ready`

// AgentHarness is a reusable coding-harness template.
type AgentHarness struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`
	Spec              AgentHarnessSpec   `json:"spec,omitempty"`
	Status            AgentHarnessStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// AgentHarnessList contains a list of AgentHarness.
type AgentHarnessList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []AgentHarness `json:"items"`
}

// SessionBudgets bounds one run. Mirrors the Agent CRD's TaskConfig.
type SessionBudgets struct {
	// +kubebuilder:default=20
	MaxIterations int32 `json:"maxIterations,omitempty"`
	// +kubebuilder:default=3600
	MaxRuntimeSeconds int32 `json:"maxRuntimeSeconds,omitempty"`
	// +kubebuilder:default=500
	MaxToolCalls int32 `json:"maxToolCalls,omitempty"`
}

// CodingSessionSpec is one run against one workspace.
type CodingSessionSpec struct {
	// +kubebuilder:validation:Required
	HarnessRef string `json:"harnessRef"`
	// +kubebuilder:validation:Required
	Prompt string `json:"prompt"`

	Repo *RepoSpec `json:"repo,omitempty"`

	// +kubebuilder:validation:Enum=autonomous;interactive
	// +kubebuilder:default=autonomous
	Mode string `json:"mode,omitempty"`

	Budgets *SessionBudgets `json:"budgets,omitempty"`

	// TTLSecondsAfterFinished cleans up terminal sessions. This is the capability
	// spike A could not reach: a Deployment never finishes.
	// +kubebuilder:default=86400
	TTLSecondsAfterFinished *int32 `json:"ttlSecondsAfterFinished,omitempty"`
}

// CodingSessionStatus is the object spike A identified as the biggest gap —
// AgentStatus carries no run, branch, or PR information at all.
type CodingSessionStatus struct {
	// +kubebuilder:validation:Enum=Pending;Working;Completed;Failed;Canceled
	Phase string `json:"phase,omitempty"`

	// Branch produced by the session; the durable output.
	Branch         string `json:"branch,omitempty"`
	PullRequestURL string `json:"pullRequestURL,omitempty"`
	CommitSHA      string `json:"commitSHA,omitempty"`

	JobName   string       `json:"jobName,omitempty"`
	PodName   string       `json:"podName,omitempty"`
	StartTime *metav1.Time `json:"startTime,omitempty"`
	EndTime   *metav1.Time `json:"endTime,omitempty"`

	// TranscriptPVC holds the harness's own config root so its native --resume
	// works without KAOS parsing the transcript.
	TranscriptPVC string `json:"transcriptPVC,omitempty"`

	FilesChanged int32              `json:"filesChanged,omitempty"`
	Message      string             `json:"message,omitempty"`
	Conditions   []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=cs
// +kubebuilder:printcolumn:name="Harness",type=string,JSONPath=`.spec.harnessRef`
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Branch",type=string,JSONPath=`.status.branch`
// +kubebuilder:printcolumn:name="PR",type=string,JSONPath=`.status.pullRequestURL`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// CodingSession is one coding run against one workspace.
type CodingSession struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`
	Spec              CodingSessionSpec   `json:"spec,omitempty"`
	Status            CodingSessionStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// CodingSessionList contains a list of CodingSession.
type CodingSessionList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []CodingSession `json:"items"`
}

func init() {
	SchemeBuilder.Register(&AgentHarness{}, &AgentHarnessList{},
		&CodingSession{}, &CodingSessionList{})
}
