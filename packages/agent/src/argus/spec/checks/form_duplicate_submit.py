from .common import define_check

CHECK = define_check(
    id="form-duplicate-submit",
    title="Rapid duplicate submit",
    category="forms",
    family="list",
    action="click",
    value=None,
    expected="Rapid repeated activation produces one durable operation.",
)

