import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from build_site import version_text  # noqa: E402


def test_html_assets_get_version():
    h = '<link rel="stylesheet" href="css/style.css"><script src="js/vendor/fuse.min.js"></script><script type="module" src="js/home.js"></script>'
    out = version_text(h, "abc123", "html")
    assert 'href="css/style.css?v=abc123"' in out and 'src="js/home.js?v=abc123"' in out and 'src="js/vendor/fuse.min.js?v=abc123"' in out


def test_js_local_imports_get_version_but_not_external():
    j = 'import { a } from "./common.js";\nimport { b } from "./search.js";\nconst u = new URL("../data/", import.meta.url);'
    out = version_text(j, "abc123", "js")
    assert 'from "./common.js?v=abc123"' in out and 'from "./search.js?v=abc123"' in out and '"../data/"' in out


def test_already_versioned_imports_are_left_alone():
    once = version_text('import { a } from "./common.js";', "v1", "js")
    assert version_text(once, "v2", "js") == once and once.count("?v=") == 1
