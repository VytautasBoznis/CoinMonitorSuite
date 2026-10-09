{{- define "coinmon.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* Labels for one component: (dict "ctx" $ "component" "bot") */}}
{{- define "coinmon.labels" -}}
{{ include "coinmon.selector" . }}
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .ctx.Chart.Name .ctx.Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "coinmon.selector" -}}
app.kubernetes.io/name: {{ .ctx.Chart.Name }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* An image of ours: (dict "ctx" $ "name" "coinmon-scraper") */}}
{{- define "coinmon.image" -}}
{{- $tag := .ctx.Values.images.tag | default .ctx.Chart.AppVersion -}}
image: {{ printf "%s/%s:%s" .ctx.Values.images.registry .name $tag | quote }}
imagePullPolicy: {{ .ctx.Values.images.pullPolicy | default (ternary "Always" "IfNotPresent" (eq $tag "latest")) }}
{{- end -}}

{{/* Pod-level settings every component shares. */}}
{{- define "coinmon.podCommon" -}}
{{- with .Values.images.pullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{- define "coinmon.dbHost" -}}
{{- if .Values.database.deploy -}}
{{ include "coinmon.fullname" . }}-timescaledb
{{- else -}}
{{ required "database.host is required when database.deploy=false" .Values.database.host }}
{{- end -}}
{{- end -}}

{{- define "coinmon.dbSecret" -}}
{{- if .Values.database.existingSecret -}}
{{ .Values.database.existingSecret }}
{{- else if .Values.database.deploy -}}
{{ include "coinmon.fullname" . }}-db
{{- else -}}
{{ required "database.existingSecret is required when database.deploy=false" "" }}
{{- end -}}
{{- end -}}

{{/* COINMON_DB_DSN, with the password spliced in from the Secret by Kubernetes' $(VAR) expansion. */}}
{{- define "coinmon.dbEnv" -}}
- name: COINMON_DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "coinmon.dbSecret" . }}
      key: password
- name: COINMON_DB_DSN
  value: "postgresql://{{ .Values.database.user }}:$(COINMON_DB_PASSWORD)@{{ include "coinmon.dbHost" . }}:{{ .Values.database.port }}/{{ .Values.database.name }}"
- name: PYTHONUNBUFFERED
  value: "1"
{{- end -}}

{{/* Holds a worker until Postgres accepts connections (it starts slower than the workers do):
     (dict "ctx" $ "name" "coinmon-scraper") */}}
{{- define "coinmon.waitForDb" -}}
initContainers:
  - name: wait-for-db
    {{- include "coinmon.image" . | nindent 4 }}
    command:
      - python
      - -c
      - |
        import os, time, psycopg
        while True:
            try:
                psycopg.connect(os.environ["COINMON_DB_DSN"], connect_timeout=3).close()
                break
            except Exception as e:
                print("waiting for the database:", e, flush=True)
                time.sleep(3)
    env:
      {{- include "coinmon.dbEnv" .ctx | nindent 6 }}
{{- end -}}

{{/* Hyperliquid settings: (dict "ctx" $ "optional" true). The bot requires the Secret; the
     dashboard runs without it (no account panels, PANIC off). */}}
{{- define "coinmon.hlEnv" -}}
- name: COINMON_HL_TESTNET
  value: {{ .ctx.Values.hyperliquid.testnet | quote }}
- name: COINMON_HL_ADDRESS
  valueFrom:
    secretKeyRef:
      name: {{ .ctx.Values.hyperliquid.secretName }}
      key: address
      optional: {{ .optional }}
- name: COINMON_HL_AGENT_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .ctx.Values.hyperliquid.secretName }}
      key: agentKey
      optional: {{ .optional }}
{{- end -}}
