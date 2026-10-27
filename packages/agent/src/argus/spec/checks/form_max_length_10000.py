from .common import define_check

CHECK = define_check(
    id="form-max-length-10000",
    title="10000-character text length",
    category="forms",
    family="form",
    action="fill",
    value="A" * 10000,
    expected="A 10000-character value is handled safely without a crash or silent corruption.",
    flow="length",
)
