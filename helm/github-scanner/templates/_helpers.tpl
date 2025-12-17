{{/*
Expand the name of the chart.
*/}}
{{- define "github-scanner.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "github-scanner.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "github-scanner.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "github-scanner.labels" -}}
helm.sh/chart: {{ include "github-scanner.chart" . }}
{{ include "github-scanner.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "github-scanner.selectorLabels" -}}
app.kubernetes.io/name: {{ include "github-scanner.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "github-scanner.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "github-scanner.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Database URL
*/}}
{{- define "github-scanner.databaseUrl" -}}
{{- if .Values.database.external.enabled }}
{{- if .Values.database.external.existingSecret }}
{{- printf "valueFrom:\n  secretKeyRef:\n    name: %s\n    key: %s" .Values.database.external.existingSecret .Values.database.external.existingSecretKey }}
{{- else }}
{{- printf "postgresql://%s:%s@%s:%d/%s" .Values.database.external.username .Values.database.external.password .Values.database.external.host (int .Values.database.external.port) .Values.database.external.database }}
{{- end }}
{{- else }}
{{- printf "postgresql://%s:%s@%s-postgres:5432/%s" .Values.database.internal.config.username .Values.database.internal.config.password (include "github-scanner.fullname" .) .Values.database.internal.config.database }}
{{- end }}
{{- end }}

{{/*
GitHub Token
*/}}
{{- define "github-scanner.githubToken" -}}
{{- if .Values.github.existingSecret }}
{{- printf "valueFrom:\n  secretKeyRef:\n    name: %s\n    key: %s" .Values.github.existingSecret .Values.github.existingSecretKey }}
{{- else }}
{{- .Values.github.token }}
{{- end }}
{{- end }}

{{/*
Image pull policy
*/}}
{{- define "github-scanner.imagePullPolicy" -}}
{{- default .Values.global.imagePullPolicy "Always" }}
{{- end }}

{{/*
Image tag
*/}}
{{- define "github-scanner.imageTag" -}}
{{- default .Values.global.imageTag "main" }}
{{- end }}

{{/*
Full image name for a component
*/}}
{{- define "github-scanner.image" -}}
{{- $registry := .root.Values.global.registry }}
{{- $repository := .component.image.repository }}
{{- $tag := default (include "github-scanner.imageTag" .root) .component.image.tag }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "github-scanner.namespace" -}}
{{- default .Release.Namespace .Values.namespaceOverride }}
{{- end }}
