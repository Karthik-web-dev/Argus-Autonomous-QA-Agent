"""Vision is a stretch capability; route only unsupported semantic surfaces here."""


def should_inspect_surface(*, tag_name: str, cross_origin: bool = False) -> bool:
    return tag_name.lower() in {"canvas", "video"} or cross_origin
