import base64
import json
import os
import ssl
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def get_opensearch_config() -> dict:
    return {
        "url": os.getenv("OPENSEARCH_URL", "").strip().rstrip("/"),
        "index": os.getenv(
            "OPENSEARCH_INDEX",
            "solar-rs485-monitor",
        ).strip(),
        "username": os.getenv("OPENSEARCH_USERNAME", "").strip(),
        "password": os.getenv("OPENSEARCH_PASSWORD", ""),
        "timeout": float(os.getenv("OPENSEARCH_TIMEOUT", "5.0")),
        "verify_tls": os.getenv(
            "OPENSEARCH_VERIFY_TLS",
            "true",
        ).strip().lower() not in ("0", "false", "no", "off"),
    }


def validate_opensearch_config(config: dict) -> None:
    if not config.get("url"):
        raise RuntimeError("OPENSEARCH_URL is not set")

    if not config.get("index"):
        raise RuntimeError("OPENSEARCH_INDEX is not set")

    if bool(config.get("username")) != bool(config.get("password")):
        raise RuntimeError(
            "OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD must be set together"
        )


def get_ssl_context(verify_tls: bool):
    if verify_tls:
        return None

    return ssl._create_unverified_context()


def get_authorization_header(username: str, password: str) -> str | None:
    if not username:
        return None

    token = base64.b64encode(f"{username}:{password}".encode("utf-8"))
    return "Basic " + token.decode("ascii")


def write_to_opensearch(data: dict, config: dict) -> dict:
    validate_opensearch_config(config)

    index = quote(config["index"], safe="")
    url = f"{config['url']}/{index}/_doc"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    authorization = get_authorization_header(
        config["username"],
        config["password"],
    )
    if authorization:
        headers["Authorization"] = authorization

    request = Request(
        url=url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=config["timeout"],
            context=get_ssl_context(config["verify_tls"]),
        ) as response:
            response_body = response.read().decode("utf-8")

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenSearch request failed status={e.code} body={error_body}"
        ) from e

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError:
        raise RuntimeError(f"Unexpected OpenSearch response: {response_body}")

    return {
        "index": result.get("_index"),
        "id": result.get("_id"),
        "result": result.get("result"),
    }
