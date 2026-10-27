from .common import define_check

CHECK = define_check(
    id="form-max-length-1024",
    title="1024-character text length",
    category="forms",
    family="form",
    action="fill",
    value="A" * 1024,
    expected="A 1024-character value is handled according to the documented field limit.",
    flow="length",
)
