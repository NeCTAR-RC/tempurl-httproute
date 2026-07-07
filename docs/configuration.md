# Configuration

[← Back to README](../README.md) · [Architecture](architecture.md) · [Deployment](deployment.md) · [Operations](operations.md)

`values.yaml` is the single source of truth and the field-by-field reference: every key is
documented inline with a commented example, including `gateway`, `hostname`, `backend`,
`rewrites`, and `refresh`. Read it alongside this page; it renders both the routing resources
and the refresher for one hostname and any number of paths. This page covers only the concepts
and rules that the inline comments cannot capture. For how these values drive the proxy at
runtime, see [Architecture](architecture.md).

## One release, one hostname

A release serves exactly one public hostname (`hostname`), and everything it renders lands in
the release namespace. Each entry in `rewrites` maps to one `HTTPRoute` rule and one
`HTTPRouteFilter` (see [Architecture](architecture.md#how-it-works)). To serve another
hostname, install another release; settings shared across releases (gateway, refresh
schedule, image) can live in a common values file passed alongside each release's own
(`-f common.yaml -f docs.yaml`).

## Signing keys

Each rewrite's signing key lives in the release namespace's keys Secret
(`refresh.keySecretName`, default `<fullname>-keys`) under a data key named after the
rewrite's `path` (e.g. `wiki`). The Secret can be populated two ways:

- **Inline** (`keys` set in values): the chart renders the Secret itself, making
  `helm install --create-namespace` a one-liner. The trade-off is that the keys pass through
  the values file and Helm release storage (`helm get values`), so such a values file must
  stay out of git.
- **Pre-created** (`keys` empty, the default): key material never touches Helm. Create the
  Secret yourself, or have a controller such as Sealed Secrets or External Secrets Operator
  produce it, then install.

A render-time pre-flight ([templates/validate.yaml](../templates/validate.yaml)) fails the
install with a descriptive error when a rewrite's key is missing in either mode.

## Backend

The route sends traffic to a `Backend` in the release namespace. By default
(`backend.create: true`) the chart creates it from `backend.hostname`/`backend.port`, named
after the release (or `backend.name` if set). Set `backend.create: false` to reference a
pre-existing `Backend` in the release namespace by `backend.name` instead.

Chart-created Backends always use TLS with certificate validation against a CA bundle. There
is no way to disable TLS or certificate verification through this chart. The `backend.tls`
block is optional and only needed to override the secure defaults (`sni` defaults to
`backend.hostname`, `wellKnownCACertificates` defaults to `System`).

## Layout

```
Chart.yaml
values.yaml                       # single source of truth
files/refresh.py                  # refresher script (loaded via .Files.Get)
templates/
  _helpers.tpl
  httproute.yaml                  # 1 HTTPRoute, 1 rule per rewrite
  httproutefilter.yaml            # 1 HTTPRouteFilter per rewrite
  backend.yaml                    # the Backend (when backend.create is true)
  secret.yaml                     # the keys Secret (when keys is set in values)
  validate.yaml                   # render-time check that every rewrite has a signing key
  rbac.yaml                       # ServiceAccount, Role, RoleBinding (release namespace only)
  proxies-configmap.yaml          # proxies.json rendered from values
  refresh-script-configmap.yaml   # refresh.py
  cronjob.yaml                    # daily refresher
  refresh-hook.yaml               # post-upgrade hook; runs refresh immediately after upgrade
```
