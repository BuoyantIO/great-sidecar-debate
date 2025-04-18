---
apiVersion: batch/v1
kind: Job
metadata:
  name: wrk2
  namespace: faces
  labels:
    buoyant.io/application: faces
    faces.buoyant.io/component: wrk2
spec:
  {{- if (gt .wrk2.replicas 1) }}
  completions: 3
  parallelism: 3
  {{- end }}
  template:
    metadata:
      labels:
        buoyant.io/application: faces
        faces.buoyant.io/component: wrk2
    spec:
      {{- if (or (index .wrk2 "affinity") (index .wrk2 "antiaffinity")) }}
      affinity:
        {{- if (index .wrk2 "affinity") }}
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: buoyant.io/meshtest-role
                operator: In
                values:
                - load
        {{- end -}}
        {{- if (index .wrk2 "antiaffinity") }}
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: faces.buoyant.io/component
                  operator: In
                  values:
                  - wrk2
              topologyKey: kubernetes.io/hostname
        {{- end -}}
      {{- end }}
      restartPolicy: Never
      containers:
      - name: wrk2
        image: gildas/wrk2:latest
        imagePullPolicy: IfNotPresent
        command:
        - /wrk
        - -t8
        - -c200
        - -d300s
        - -R{{ .wrk2.rps }}
        - --latency
        - http://face/
        resources:
          requests:
            cpu: 25m
            memory: 64Mi
          limits:
            memory: 128Mi
