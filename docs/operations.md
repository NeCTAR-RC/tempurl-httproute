# Operations

[← Back to README](../README.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · [Deployment](deployment.md)

How to confirm a deployment is working, diagnose problems, and the security properties of the
chart. To re-run the refresher job, see
[Deployment: Signatures populate automatically](deployment.md#4-signatures-populate-automatically).

## Verify and troubleshoot

Confirm the filter was patched and the proxy serves end to end (filter names are
`<release>-<path>`):

```bash
# Filter patched (placeholder replaced, expiry ~7 days out):
kubectl get httproutefilter tempurl-httproute-wiki -n docs \
  -o jsonpath='{.spec.urlRewrite.path.replaceRegexMatch.substitution}'

# End to end:
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://docs.example.com/wiki/report.pdf   # expect 200
```

If a check fails, match the symptom below:

| Symptom | Likely cause |
|---------|--------------|
| `401`/`403` from the upstream | TempURL expired, wrong key, or prefix slash mismatch. Re-run the job and check the signature was patched. |
| `403` on PATCH in the job log | The Role/RoleBinding is missing or was modified. `helm upgrade` to restore the chart's RBAC. |
| `KeyError` / `data key ... not found` | The keys Secret has no data key matching the rewrite's `path`. |
| Install fails: `keys is missing entries ...` | Inline `keys` in values does not cover every rewrite. Add the missing entries (data key = the rewrite's `path`) and retry. |
| Install fails: `keys Secret ... not found` / `missing data key(s)` | Render-time pre-flight caught a missing or incomplete pre-created Secret. Create or fix it (see [Deployment step 2](deployment.md#2-provide-the-signing-keys)) and retry, or switch to inline `keys`. |
| Hook fails: `BackoffLimitExceeded`; job log shows `failed: secret ... not found` | The keys Secret has not been created yet, or its name does not match `refresh.keySecretName`/`<release>-keys`. Create it, delete the failed hook Job, then `helm upgrade`. |
| URL still serves the placeholder | The job has not run yet, or the release/namespace does not match the filter you are inspecting. |
| Route not attached (`Accepted: False` on the HTTPRoute) | The Gateway's listener does not allow routes from the release namespace. Fix `spec.listeners[].allowedRoutes.namespaces` on the Gateway. |
| Upgrade fails (hook Job already exists) | A previous hook Job failed and was not cleaned up. Delete it manually: `kubectl delete job <release>-refresh -n <namespace>`. |

Inspect the refresher itself:

```bash
kubectl get cronjob tempurl-httproute -n docs
kubectl logs -l job-name -n docs --tail=50
```

## Security notes

- The signing key is sensitive. Keep it in the Secret only, never in `values.yaml`,
  `proxies.json`, env vars, or git. Rotate it if it has been exposed.
- RBAC is least-privilege and namespaced: the refresher can only `get`/`patch`
  `HTTPRouteFilter` resources and `get` `Secrets`, and only in the release namespace.
- The CronJob pod runs non-root with a read-only root filesystem and all capabilities
  dropped.
