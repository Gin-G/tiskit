{{/* Common name helpers */}}
{{- define "tiskit.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tiskit.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "tiskit.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tiskit.labels" -}}
helm.sh/chart: {{ include "tiskit.chart" . }}
{{ include "tiskit.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "tiskit.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tiskit.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "tiskit.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- include "tiskit.fullname" . -}}
{{- else -}}
default
{{- end -}}
{{- end -}}

{{/* oauth2-proxy names */}}
{{- define "tiskit.oauth2.fullname" -}}
{{- printf "%s-oauth2-proxy" (include "tiskit.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tiskit.oauth2.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tiskit.name" . }}-oauth2-proxy
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "tiskit.oauth2.labels" -}}
helm.sh/chart: {{ include "tiskit.chart" . }}
{{ include "tiskit.oauth2.selectorLabels" . }}
app.kubernetes.io/component: auth
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Format Traefik middleware annotation: "<ns>-<name>@kubernetescrd" */}}
{{- define "tiskit.middlewareRef" -}}
{{- printf "%s-%s@kubernetescrd" .ns .name -}}
{{- end -}}
