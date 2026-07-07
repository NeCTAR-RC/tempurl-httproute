# Swift TempURL reverse-proxy with Envoy Gateway

Serve private OpenStack Swift containers through a public hostname using Envoy Gateway, with
each Swift TempURL signature refreshed automatically before it expires.

A request to `https://<hostname>/<path>/<object>` is transparently rewritten and proxied to
a signed Swift TempURL. The user never sees the signed private URL, and the signature is
rotated on a schedule so the proxy keeps working indefinitely.

This is packaged as the **`tempurl-httproute`** Helm chart. One release serves one
public hostname, with all its resources in the release namespace. A single `values.yaml` is
the source of truth: it renders the routing resources (`HTTPRoute`, `HTTPRouteFilter`,
`Backend`) **and** the refresher (`CronJob` + config) for any number of paths under that
hostname. To serve another hostname, install another release.

## How it works

```
client ──> Envoy Gateway ──(rewrite path + host, add temp_url_sig)──> <swift object store>
                 ▲
                 │ HTTPRouteFilter.substitution patched daily
        CronJob tempurl-httproute  (reads proxies.json + the keys Secret, recomputes HMAC)
```

- **The reverse proxy.** One `HTTPRoute` routes the hostname to the Swift `Backend`, with one
  rule per path. Each rule references an `HTTPRouteFilter` that rewrites the path to the
  signed Swift TempURL.
- **The refresher.** A daily `CronJob` recomputes each signature and patches the matching
  `HTTPRouteFilter` in place, so the signature never lapses. It also runs as a post-upgrade
  hook after every `helm upgrade`.
- **One namespace.** Route, filters, `Backend`, keys Secret, and refresher all live in the
  release namespace, and the refresher's RBAC is scoped to that namespace only.

Adding a path is an edit to `values.yaml`; adding a hostname is another `helm install`. See
[Architecture](docs/architecture.md) for the full picture.

## Quick start

Write a minimal `values.yaml` (this routes one path; the chart creates the upstream
`Backend` by default — set `backend.create: false` to reference an existing one instead).
Because it contains the signing key, keep this file out of git:

```yaml
hostname: docs.example.com

backend:
  hostname: object-store.example.com

rewrites:
  - path: wiki
    projectId: 0123456789abcdef0123456789abcdef
    container: wiki
    prefix: doc

keys:
  wiki: REPLACE_WITH_SWIFT_TEMPURL_KEY
```

Install. The chart creates the keys Secret from `keys`, and the post-install hook
populates fresh signatures automatically:

```bash
helm install tempurl-httproute . -n docs --create-namespace -f my-values.yaml
```

To keep key material out of Helm entirely (for example when the Secret is produced by
Sealed Secrets), leave `keys` empty and pre-create the Secret instead — see
[Deployment](docs/deployment.md).

The full walkthrough (prerequisites, verification, running multiple hostnames) is in
[Deployment](docs/deployment.md).

## Documentation

- **[Architecture](docs/architecture.md)**: how the proxy and refresher fit together, what
  the rewrite looks like, and why signing uses a prefix.
- **[Configuration](docs/configuration.md)**: the concepts behind `values.yaml` (the
  field-by-field reference is inline in `values.yaml` itself): the one-release-per-hostname
  model, the `backend` block, and the chart layout.
- **[Deployment](docs/deployment.md)**: prerequisites, the full install steps, adding
  another path or hostname, and verification.
- **[Operations](docs/operations.md)**: verifying a deployment, the troubleshooting table, and
  security notes.
