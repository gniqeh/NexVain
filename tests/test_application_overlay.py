"""Regression checks for the platform-level, display-only Dcell application form."""
from application_overlay import decorate_dcell_page
from app import render_document


def test_dcell_outer_shell_only_and_escaped_name():
    html = render_document("Test", "Description", '<iframe src="custom/dcell-7/index.html" sandbox="allow-scripts"></iframe>', "", "blue")
    original_iframe = '<iframe src="custom/dcell-7/index.html" sandbox="allow-scripts"></iframe>'
    result = decorate_dcell_page(html, 7, '农田 <测试> & "数据"')
    assert original_iframe in result
    assert 'id="nva-apply-open"' in result
    assert 'ID 7' in result
    assert '农田 &lt;测试&gt; &amp; &quot;数据&quot;' in result
    assert result.count('id="nva-apply-open"') == 1
    assert 'form.reset()' in result
    assert 'fetch(' not in result
    assert 'XMLHttpRequest' not in result
    assert result.count("<style") == result.count("</style>")
    assert result.count("<script") == result.count("</script>")


def test_normal_page_has_no_application_button():
    homepage = render_document("专题首页", "", "<p>普通内容</p>", "", "blue")
    assert 'nva-apply-open' not in homepage
    assert 'nva-apply-form' not in homepage
