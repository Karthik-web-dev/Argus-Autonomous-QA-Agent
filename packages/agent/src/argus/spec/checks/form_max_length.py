from .common import define_check

CHECK = define_check(
    id="form-max-length",
    title="256-character text length",
    category="forms",
    family="form",
    action="fill",
    value="A" * 256,
    expected="A 256-character value is handled according to the documented field limit.",
    flow="length",
)
