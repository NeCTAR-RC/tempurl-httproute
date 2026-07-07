# Deployment

[← Back to README](../README.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · [Operations](operations.md)

Full install and day-two instructions. For the complete values reference, see
[Configuration](configuration.md).

## Prerequisites

- A Kubernetes cluster running Envoy Gateway, with the `gateway.envoyproxy.io` CRDs
  (`HTTPRouteFilter`, `Backend`) installed.
- A `Gateway` to attach to (the chart references `default` in namespace `infra` by default).
  Its listener must allow route attachment from the release namespace
  (`spec.listeners[].allowedRoutes.namespaces`).
- A Swift TempURL key set on each container (the `Temp-URL-Key` property; see below), or on the
  Swift account.

## Prepare the object store

Before deploying the chart, set up the Swift side: a container to serve from, a TempURL key on
the container, and the objects uploaded under a shared prefix.

### Create a container

Create the container that a rewrite serves from (here `wiki`, matching the `container` value):

```bash
openstack container create wiki
```

### Set the TempURL key

Set a TempURL key on the container (the `Temp-URL-Key` property). This is the same key you place
in the keys Secret in [Deploy step 2](#2-provide-the-signing-keys):

```bash
openstack container set --property Temp-URL-Key=REPLACE_WITH_SWIFT_TEMPURL_KEY wiki
```

### Upload objects under a prefix

Every object served by a rewrite must share a common name prefix (see
[Architecture: Prefix-mode signing](architecture.md#prefix-mode-signing)). In practice the
prefix is the directory the static files sit under.

For example, to serve a local `doc/` directory through a rewrite with `container: wiki` and
`prefix: doc`, upload the files so their object names keep the `doc/` prefix. From the parent
directory of `doc`:

```bash
find doc -type f -print0 | xargs -0 -n50 openstack object create wiki
```

This creates objects named `doc/<file>` in the `wiki` container, all covered by the single
`prefix: doc` signature.

## Deploy

### 1. Write a `values.yaml`

Everything else (gateway, refresh schedule, expiry) has a working default. This config routes
one path and has the chart create the upstream `Backend` (set `backend.create: false` and
`backend.name` to use a `Backend` that already exists in the release namespace):

```yaml
hostname: docs.example.com

backend:
  hostname: object-store.example.com

rewrites:
  - path: wiki
    projectId: 0123456789abcdef0123456789abcdef
    container: wiki
    prefix: doc
```

### 2. Provide the signing keys

Every rewrite needs its Swift TempURL key in a Secret in the release namespace, named
`<release>-keys` by default (e.g. `tempurl-httproute-keys`), one data key per rewrite, named
after its `path`. Two ways to get it there:

**Inline in values (default path).** Add the keys to `values.yaml` and the chart renders
the Secret itself, so installing is a single command:

```yaml
keys:
  wiki: REPLACE_WITH_SWIFT_TEMPURL_KEY
```

A values file with inline keys is sensitive: keep it out of git. To keep keys in git
safely, use the pre-created Secret mode below with
[Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets). Inline keys also end up
in Helm release storage, readable via `helm get values` by anyone who can read Secrets in
the namespace.

**Pre-created Secret.** Leave `keys` empty to keep key material out of Helm entirely, and
create the Secret before installing — by hand, or from a committed
[SealedSecret](https://github.com/bitnami-labs/sealed-secrets) or similar controller:

```bash
kubectl create secret generic tempurl-httproute-keys -n docs \
  --from-literal=wiki='REPLACE_WITH_SWIFT_TEMPURL_KEY'
```

### 3. Install with Helm

```bash
helm install tempurl-httproute . -n docs --create-namespace -f my-values.yaml
```

`-n docs` is the release namespace: it holds every resource the release renders (route,
filters, `Backend`, keys Secret, CronJob, ServiceAccount, ConfigMaps).
`--create-namespace` creates it if needed (with a pre-created Secret the namespace
necessarily exists already).

### 4. Signatures populate automatically

The `HTTPRouteFilter`s render with a placeholder `substitution`. A `post-install,post-upgrade`
hook (`<release>-refresh`) runs the refresher immediately after both `helm install` and
`helm upgrade`, so signatures are populated without a manual step. A missing signing key
fails the install/upgrade at render time with a descriptive error, so a release can never
come up silently serving the unsigned placeholder: with inline `keys` the check is that every
rewrite has an entry; with a pre-created Secret it is a live lookup of the Secret and its data
keys. As a backstop for cases the lookup cannot see (offline dry-runs, or an installer that
cannot read the `kube-system` Namespace), the refresher itself also fails on a missing Secret
(`failed: secret ... not found`), which fails the hook; create the Secret, delete the failed
hook Job, and run `helm upgrade`.

Follow the hook Job's progress and expect one `PATCH ... -> 200` line per rewrite:

```bash
kubectl logs -f job/tempurl-httproute-refresh -n docs
```

To re-run the refresher on demand (for example after creating a missing Secret), trigger a
one-off Job from the CronJob:

```bash
kubectl create job --from=cronjob/tempurl-httproute tempurl-httproute-init -n docs
kubectl logs -f job/tempurl-httproute-init -n docs
```

Once signatures are populated, confirm the deployment works: see
[Operations: Verify and troubleshoot](operations.md#verify-and-troubleshoot).

## Add another path

1. Append a `rewrites` entry in `values.yaml`.
2. Add its signing key: a new `keys` entry, or a new data key in the pre-created Secret
   (either way, named after the `path`).
3. Run `helm upgrade`. The post-upgrade hook refreshes signatures automatically.

## Add another hostname

A hostname is a release. Install the chart again with its own values file, typically in its
own namespace (repeat steps 1–3 above). Settings shared across releases can live in a common
values file:

```bash
helm install wiki-proxy . -n wiki --create-namespace -f common.yaml -f wiki-values.yaml
```

Check the Gateway's `allowedRoutes` covers the new namespace (see
[Prerequisites](#prerequisites)).
