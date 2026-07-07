#!/usr/bin/env python3
"""Regenerate Swift TempURL signatures and patch each proxy's HTTPRouteFilter.

Reads /config/proxies.json. For every record it recomputes the Swift TempURL
HMAC (prefix mode, see the README), then PATCHes
.spec.urlRewrite.path.replaceRegexMatch.substitution on the named HTTPRouteFilter
via the in-cluster Kubernetes REST API.

The signing key is read from the release's keys Secret (data key = the rewrite
path), also via the API rather than a volume mount, so a key rotation takes
effect on the next run without restarting anything. Standard library only.
"""
import base64
import hmac
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from hashlib import sha256

CONFIG_PATH = "/config/proxies.json"
SA = "/var/run/secrets/kubernetes.io/serviceaccount"
API_HOST = "https://kubernetes.default.svc"
DEFAULT_EXPIRY = 604800  # 7 days


class SecretNotFound(Exception):
    pass


def load_token():
    with open(SA + "/token") as f:
        return f.read().strip()


def read_key(namespace, secret_name, data_key, token, ctx):
    api = "%s/api/v1/namespaces/%s/secrets/%s" % (API_HOST, namespace, secret_name)
    req = urllib.request.Request(api, method="GET")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            secret = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SecretNotFound("secret %s/%s not found" % (namespace, secret_name))
        raise
    data = secret.get("data", {})
    if data_key not in data:
        raise KeyError(
            "data key '%s' not found in secret %s/%s" % (data_key, namespace, secret_name)
        )
    return base64.b64decode(data[data_key]).decode("utf-8").strip()


def build_substitution(proxy, now, token, ctx):
    url = "/v1/AUTH_%s/%s/%s" % (
        proxy["projectId"],
        proxy["container"],
        proxy["prefix"],
    )
    expires = now + int(proxy.get("expirySeconds", DEFAULT_EXPIRY))
    # Swift prefix-mode TempURL: the signed prefix path and temp_url_prefix both
    # carry a trailing slash (verified against a working signature).
    hmac_body = "GET\n%s\nprefix:%s/" % (expires, url)
    key = read_key(
        proxy["namespace"], proxy["keySecretName"], proxy["dataKey"], token, ctx
    ).encode("utf-8")
    signature = hmac.new(key, hmac_body.encode("utf-8"), sha256).hexdigest()
    substitution = (
        "%s/\\1?temp_url_sig=%s&temp_url_expires=%s&temp_url_prefix=%s/&inline&"
        % (url, signature, expires, proxy["prefix"])
    )
    return substitution, expires


def patch_filter(proxy, substitution, token, ctx):
    api = (
        "%s/apis/gateway.envoyproxy.io/v1alpha1"
        "/namespaces/%s/httproutefilters/%s"
        % (API_HOST, proxy["namespace"], proxy["filterName"])
    )
    patch = {"spec": {"urlRewrite": {"path": {"replaceRegexMatch": {"substitution": substitution}}}}}
    body = json.dumps(patch).encode("utf-8")
    req = urllib.request.Request(api, data=body, method="PATCH")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/merge-patch+json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return resp.status


def main():
    with open(CONFIG_PATH) as f:
        proxies = json.load(f)["proxies"]

    token = load_token()
    ctx = ssl.create_default_context(cafile=SA + "/ca.crt")
    now = int(time.time())

    failures = 0
    for proxy in proxies:
        name = proxy.get("name", proxy.get("filterName", "?"))
        try:
            substitution, expires = build_substitution(proxy, now, token, ctx)
            status = patch_filter(proxy, substitution, token, ctx)
            days = (expires - now) // 86400
            print(
                "[%s] PATCH %s/%s -> %s (expires in %sd)"
                % (name, proxy["namespace"], proxy["filterName"], status, days)
            )
        except urllib.error.HTTPError as e:
            failures += 1
            detail = e.read().decode("utf-8", "replace")
            sys.stderr.write(
                "[%s] PATCH failed: %s %s\n%s\n" % (name, e.code, e.reason, detail)
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            sys.stderr.write("[%s] failed: %s\n" % (name, e))

    if failures:
        sys.stderr.write("%d of %d proxies failed\n" % (failures, len(proxies)))
        sys.exit(1)
    print("All %d proxies refreshed" % len(proxies))


if __name__ == "__main__":
    main()
