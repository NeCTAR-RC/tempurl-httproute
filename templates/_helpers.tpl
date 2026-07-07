{{/*
Chart fullname. Defaults to the release name, but avoids doubling up when the
release is already named after the chart.
*/}}
{{- define "tempurl-httproute.fullname" -}}
{{- $name := .Chart.Name -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Common labels applied to every rendered resource.
*/}}
{{- define "tempurl-httproute.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
DNS-1123 slug: lowercase, non-alphanumerics collapsed to single dashes, trimmed.
Usage: include "tempurl-httproute.slug" "Some/Value"
*/}}
{{- define "tempurl-httproute.slug" -}}
{{- . | lower | regexReplaceAll "[^a-z0-9]+" "-" | trimAll "-" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Secret data key for a rewrite: the path, DNS-1123 safe.
Usage: include "tempurl-httproute.dataKey" $rewrite
*/}}
{{- define "tempurl-httproute.dataKey" -}}
{{- include "tempurl-httproute.slug" .path -}}
{{- end -}}

{{/*
HTTPRouteFilter name for a rewrite: "<fullname>-<path>", DNS-1123 safe.
Usage: include "tempurl-httproute.filterName" (dict "root" $ "rewrite" $rw)
*/}}
{{- define "tempurl-httproute.filterName" -}}
{{- $fullname := include "tempurl-httproute.fullname" .root -}}
{{- include "tempurl-httproute.slug" (printf "%s-%s" $fullname .rewrite.path) -}}
{{- end -}}

{{/*
Backend name: backend.name if set, else the release fullname.
*/}}
{{- define "tempurl-httproute.backendName" -}}
{{- if .Values.backend.name -}}
{{- .Values.backend.name -}}
{{- else -}}
{{- include "tempurl-httproute.fullname" . -}}
{{- end -}}
{{- end -}}

{{/*
Keys Secret name: refresh.keySecretName if set, else "<fullname>-keys".
*/}}
{{- define "tempurl-httproute.keySecretName" -}}
{{- if .Values.refresh.keySecretName -}}
{{- .Values.refresh.keySecretName -}}
{{- else -}}
{{- printf "%s-keys" (include "tempurl-httproute.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Shared job spec for the refresh CronJob and post-upgrade hook Job.
*/}}
{{- define "tempurl-httproute.refreshJobSpec" -}}
{{- $fullname := include "tempurl-httproute.fullname" . -}}
backoffLimit: 2
template:
  spec:
    serviceAccountName: {{ $fullname }}
    restartPolicy: Never
    securityContext:
      runAsNonRoot: true
      runAsUser: 65534
      seccompProfile:
        type: RuntimeDefault
    containers:
      - name: refresh
        image: {{ .Values.refresh.image | quote }}
        command: ["python", "/scripts/refresh.py"]
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        volumeMounts:
          - name: script
            mountPath: /scripts
            readOnly: true
          - name: config
            mountPath: /config
            readOnly: true
    volumes:
      - name: script
        configMap:
          name: {{ $fullname }}-script
      - name: config
        configMap:
          name: {{ $fullname }}-proxies
{{- end -}}
