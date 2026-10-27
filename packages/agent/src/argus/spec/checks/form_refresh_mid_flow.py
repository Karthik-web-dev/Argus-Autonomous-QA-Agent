from .common import define_check

CHECK = define_check(
    id="form-refresh-mid-flow",
    title="Refresh during a form flow",
    category="forms",
    family="form",
    action="fill",
    value=None,
    expected="Refreshing mid-flow leaves the application in a consistent state.",
    flow="refresh",
)

