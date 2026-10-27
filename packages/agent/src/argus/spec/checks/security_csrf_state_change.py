from .common import define_check

CHECK = define_check(
    id="security-csrf-state-change",
    title="Cross-site state change",
    category="security",
    family="list",
    action="click",
    value=None,
    expected="State-changing actions reject requests without valid same-site protections.",
)

