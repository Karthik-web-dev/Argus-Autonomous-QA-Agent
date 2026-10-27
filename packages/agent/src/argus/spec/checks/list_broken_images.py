from .common import define_check

CHECK = define_check(
    id="list-broken-images",
    title="Broken images",
    category="lists",
    family="any",
    action="assert_no_broken_images",
    value=None,
    expected="A missing image has a useful fallback and does not break list layout.",
)

