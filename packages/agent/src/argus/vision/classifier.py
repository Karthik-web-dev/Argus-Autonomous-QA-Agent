def classify_surface(tag_name: str, cross_origin: bool = False) -> str:
    if cross_origin:
        return "cross_origin_frame"
    return {"canvas": "canvas", "video": "video"}.get(tag_name.lower(), "semantic")
