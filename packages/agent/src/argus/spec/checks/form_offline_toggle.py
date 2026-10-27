from .common import define_check

CHECK = define_check(
    id="form-offline-toggle",
    title="Offline toggle during request",
    category="forms",
    family="form",
    action="fill",
    value=None,
    expected="Losing connectivity during a request produces recoverable feedback and consistent state.",
    flow="offline",
)
