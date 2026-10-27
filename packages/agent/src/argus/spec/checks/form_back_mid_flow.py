from .common import define_check

CHECK = define_check(
    id="form-back-mid-flow",
    title="Back during a form flow",
    category="forms",
    family="form",
    action="fill",
    value=None,
    expected="Returning to a form preserves safe state and does not duplicate a mutation.",
    flow="back",
)

