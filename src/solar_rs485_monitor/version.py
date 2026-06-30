from importlib.metadata import PackageNotFoundError, version


PACKAGE_NAME = "solar-rs485-monitor"


def get_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0+unknown"
