from .common import define_check

CHECK = define_check(
    id="form-throttled-network",
    title="Throttled network submission",
    category="forms",
    family="form",
    action="fill",
    value=None,
    expected="A delayed response does not cause duplicate or lost form submissions.",
    flow="throttled",
)

