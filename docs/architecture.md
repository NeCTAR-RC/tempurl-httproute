# Architecture

[← Back to README](../README.md) · [Configuration](configuration.md) · [Deployment](deployment.md) · [Operations](operations.md)

How the reverse proxy is put together and how the rewrite works. For the values that drive
it, see [Configuration](configuration.md).

## How it works

```
client ──> Envoy Gateway ──(rewrite path + host, add temp_url_sig)──> <swift object store>
                 ▲
                 │ HTTPRouteFilter.substitution patched daily
        CronJob tempurl-httproute  (reads proxies.json + the keys Secret, recomputes HMAC)
```

One release serves one public hostname, and every resource it renders lives in the release
namespace:

- **The reverse proxy.** One `HTTPRoute` routes the hostname to the Swift `Backend`
  (chart-created or pre-existing in the same namespace), with one rule per path. Each rule
  references an `HTTPRouteFilter` that rewrites the path to the signed Swift TempURL. The
  signature and expiry live inside the filter's `substitution` string.
- **The refresher.** A daily `CronJob` recomputes each TempURL signature from the keys
  Secret and patches the matching `HTTPRouteFilter` in place, so the signature never lapses.
  The same job also runs as a post-upgrade hook so signature updates take effect immediately
  after a `helm upgrade`. Its RBAC is a namespaced `Role`: the refresher can only touch
  `HTTPRouteFilter`s and `Secret`s in its own namespace.

Adding a path is an edit to `values.yaml`, not a new workload. Adding a hostname is another
release: each hostname gets its own namespace, keys Secret, and refresher, so releases are
fully independent of each other.

## What the rewrite looks like

Given a release for host `docs.example.com` with a rewrite `path: wiki`, `container: wiki`,
`prefix: doc`, a public request:

```
GET https://docs.example.com/wiki/report.pdf
```

is matched by the rewrite's `HTTPRouteFilter` (regex `^/wiki/([^?]+)(?:\?(.*))?$`, which
captures `report.pdf`). The filter strips the `Authorization` header, rewrites the host to the
Swift `Backend`, and rewrites the path to a signed Swift TempURL:

```
/v1/AUTH_<projectId>/wiki/doc/report.pdf?temp_url_sig=<hmac-sha256>&temp_url_expires=<unix-ts>&temp_url_prefix=doc/&inline&
```

Here `wiki` is the public `path`, `doc` is the Swift `prefix`, and the `CronJob` refreshes
`temp_url_sig`/`temp_url_expires` daily. The client never sees the signed URL.

The signing convention is Swift prefix-mode with a trailing slash: the refresher computes
`temp_url_sig` as an HMAC-SHA256 over
`GET\n<expires>\nprefix:/v1/AUTH_<projectId>/<container>/<prefix>/` (note the trailing slash)
and sets `temp_url_prefix=<prefix>/`.

## Prefix-mode signing

Swift TempURL signatures are applied to objects, not to a container as a whole. Prefix-mode
lets one signature authorise every object whose name starts with a common prefix, so the
signed URL validates for all files served by a rewrite rather than for a single object. Every
object behind a rewrite must therefore share a common name prefix, and `prefix` must be set to
it. In practice the prefix is the directory the static files sit under.

For how to upload objects under a shared prefix, see
[Deployment: Upload objects under a prefix](deployment.md#upload-objects-under-a-prefix).
