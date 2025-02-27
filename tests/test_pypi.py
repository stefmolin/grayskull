import hashlib
import json
import os
import sys

import pytest
from colorama import Fore, Style

from grayskull.cli import CLIConfig
from grayskull.pypi import PyPi
from grayskull.pypi.pypi import clean_deps_for_conda_forge


@pytest.fixture
def pypi_metadata():
    path_metadata = os.path.join(
        os.path.dirname(__file__), "data", "pypi_pytest_metadata.json"
    )
    with open(path_metadata) as f:
        return json.load(f)


def test_extract_pypi_requirements(pypi_metadata):
    recipe = PyPi(name="pytest", version="5.3.1")
    pypi_reqs = recipe._extract_requirements(pypi_metadata["info"])
    assert sorted(pypi_reqs["host"]) == sorted(["python", "pip"])
    assert sorted(pypi_reqs["run"]) == sorted(
        [
            "python",
            "py >=1.5.0",
            "packaging",
            "attrs >=17.4.0",
            "more-itertools >=4.0.0",
            "pluggy <1.0,>=0.12",
            "wcwidth",
            "pathlib2 >=2.2.0  # [py<36]",
            "importlib-metadata >=0.12  # [py<38]",
            "atomicwrites >=1.0  # [win]",
            "colorama   # [win]",
        ]
    )


def test_get_pypi_metadata(pypi_metadata):
    recipe = PyPi(name="pytest", version="5.3.1", is_strict_cf=True)
    metadata = recipe._get_pypi_metadata(name="pytest", version="5.3.1")
    assert metadata["name"] == "pytest"
    assert metadata["version"] == "5.3.1"
    assert "pathlib2 >=2.2.0  # [py<36]" not in recipe["requirements"]["run"]


def test_get_name_version_from_requires_dist():
    assert PyPi._get_name_version_from_requires_dist("py (>=1.5.0)") == (
        "py",
        ">=1.5.0",
    )


def test_get_extra_from_requires_dist():
    assert PyPi._get_extra_from_requires_dist(' python_version < "3.6"') == [
        ("", "python_version", "<", "3.6", "", "",)
    ]
    assert PyPi._get_extra_from_requires_dist(
        " python_version < \"3.6\" ; extra =='test'"
    ) == [
        ("", "python_version", "<", "3.6", "", ""),
        ("", "extra", "==", "test", "", ""),
    ]
    assert PyPi._get_extra_from_requires_dist(
        ' (sys_platform =="win32" and python_version =="2.7") and extra =="socks"'
    ) == [
        ("(", "sys_platform", "==", "win32", "", "and"),
        ("", "python_version", "==", "2.7", ")", "and"),
        ("", "extra", "==", "socks", "", ""),
    ]


def test_get_all_selectors_pypi():
    recipe = PyPi(name="pytest", version="5.3.1")
    assert recipe._get_all_selectors_pypi(
        [
            ("(", "sys_platform", "==", "win32", "", "and"),
            ("", "python_version", "==", "2.7", ")", "and"),
            ("", "extra", "==", "socks", "", ""),
        ]
    ) == ["(", "win", "and", "py==27", ")"]


def test_get_selector():
    assert PyPi._parse_extra_metadata_to_selector("extra", "==", "win32") == ""
    assert (
        PyPi._parse_extra_metadata_to_selector("sys_platform", "==", "win32") == "win"
    )
    assert (
        PyPi._parse_extra_metadata_to_selector("python_version", "<", "3.6") == "py<36"
    )


@pytest.mark.parametrize(
    "requires_python, exp_selector, ex_cf",
    [
        (">=3.5", "2k", None),
        (">=3.6", "2k", None),
        (">=3.7", "<37", "<37"),
        ("<=3.7", ">=38", ">=38"),
        ("<=3.7.1", ">=38", ">=38"),
        ("<3.7", ">=37", ">=37"),
        (">2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*", "<36", "<36"),
        (">=2.7, !=3.6.*", "==36", "==36"),
        (">3.7", "<38", "<38"),
        (">2.7", "2k", "<36"),
        ("<3", "3k", "skip"),
        ("!=3.7", "==37", "==37"),
    ],
)
def test_py_version_to_selector(requires_python, exp_selector, ex_cf):
    metadata = {"requires_python": requires_python}
    assert PyPi.py_version_to_selector(metadata) == f"# [py{exp_selector}]"

    if ex_cf != "skip":
        expected = f"# [py{ex_cf}]" if ex_cf else None
        result = PyPi.py_version_to_selector(metadata, is_strict_cf=True)
        if isinstance(expected, str):
            assert expected == result
        else:
            assert expected is result


@pytest.mark.parametrize(
    "requires_python, exp_limit, ex_cf",
    [
        (">=3.5", ">=3.5", None),
        (">=3.6", ">=3.6", None),
        (">=3.7", ">=3.7", ">=3.7"),
        ("<=3.7", "<3.8", "<3.8"),
        ("<=3.7.1", "<3.8", "<3.8"),
        ("<3.7", "<3.7", "<3.7"),
        (">2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*", ">=3.6", ">=3.6"),
        (">=2.7, !=3.6.*", "!=3.6", "!=3.6"),
        (">3.7", ">=3.8", ">=3.8"),
        (">2.7", ">=3.6", ">=3.6"),
        ("<3", "<3.0", "skip"),
        ("!=3.7", "!=3.7", "!=3.7"),
    ],
)
def test_py_version_to_limit_python(requires_python, exp_limit, ex_cf):
    metadata = {"requires_python": requires_python}
    assert PyPi.py_version_to_limit_python(metadata) == f"{exp_limit}"

    if ex_cf != "skip":
        result = PyPi.py_version_to_limit_python(metadata, is_strict_cf=True)
        if isinstance(ex_cf, str):
            assert ex_cf == result
        else:
            assert ex_cf is result


def test_get_sha256_from_pypi_metadata():
    metadata = {
        "urls": [
            {"packagetype": "egg", "digests": {"sha256": "23123"}},
            {"packagetype": "sdist", "digests": {"sha256": "1234sha256"}},
        ]
    }
    assert PyPi.get_sha256_from_pypi_metadata(metadata) == "1234sha256"

    metadata = {
        "urls": [
            {"packagetype": "egg", "digests": {"sha256": "23123"}},
            {"packagetype": "wheel", "digests": {"sha256": "1234sha256"}},
        ]
    }
    with pytest.raises(AttributeError) as err:
        PyPi.get_sha256_from_pypi_metadata(metadata)
    assert err.match("Hash information for sdist was not found on PyPi metadata.")


@pytest.mark.github
@pytest.mark.parametrize(
    "name", ["hypothesis", "https://github.com/HypothesisWorks/hypothesis"]
)
def test_injection_distutils(name):
    recipe = PyPi(name=name, version="5.5.1")
    data = recipe._get_sdist_metadata(
        "https://pypi.io/packages/source/h/hypothesis/hypothesis-5.5.1.tar.gz",
        "hypothesis",
    )
    assert sorted(data["install_requires"]) == sorted(
        ["attrs>=19.2.0", "sortedcontainers>=2.1.0,<3.0.0"]
    )
    assert data["entry_points"] == {
        "pytest11": ["hypothesispytest = hypothesis.extra.pytestplugin"]
    }
    assert data["version"] == "5.5.1"
    assert data["name"] == "hypothesis"
    assert not data.get("compilers")


@pytest.mark.github
@pytest.mark.parametrize("name", ["pytest", "https://github.com/pytest-dev/pytest"])
def test_injection_distutils_pytest(name):
    recipe = PyPi(name=name, version="5.3.2")
    data = recipe._get_sdist_metadata(
        "https://pypi.io/packages/source/p/pytest/pytest-5.3.2.tar.gz", "pytest"
    )
    assert sorted(data["install_requires"]) == sorted(
        [
            "py>=1.5.0",
            "packaging",
            "attrs>=17.4.0",
            "more-itertools>=4.0.0",
            'atomicwrites>=1.0;sys_platform=="win32"',
            'pathlib2>=2.2.0;python_version<"3.6"',
            'colorama;sys_platform=="win32"',
            "pluggy>=0.12,<1.0",
            'importlib-metadata>=0.12;python_version<"3.8"',
            "wcwidth",
        ]
    )
    assert sorted(data["setup_requires"]) == sorted(
        ["setuptools>=40.0", "setuptools_scm"]
    )
    assert not data.get("compilers")


@pytest.mark.github
@pytest.mark.parametrize("name", ["gsw", "https://github.com/TEOS-10/GSW-python"])
def test_injection_distutils_compiler_gsw(name):
    recipe = PyPi(name=name, version="3.3.1")
    data = recipe._get_sdist_metadata(
        "https://pypi.io/packages/source/g/gsw/gsw-3.3.1.tar.gz", "gsw"
    )
    assert data.get("compilers") == ["c"]
    assert data["packages"] == ["gsw"]


def test_injection_distutils_setup_reqs_ensure_list():
    pkg_name, pkg_ver = "pyinstaller-hooks-contrib", "2020.7"
    recipe = PyPi(name=pkg_name, version=pkg_ver)
    data = recipe._get_sdist_metadata(
        f"https://pypi.io/packages/source/p/{pkg_name}/{pkg_name}-{pkg_ver}.tar.gz",
        pkg_name,
    )
    assert data.get("setup_requires") == ["setuptools >= 30.3.0"]


def test_merge_pypi_sdist_metadata():
    recipe = PyPi(name="gsw", version="3.3.1")
    pypi_metadata = recipe._get_pypi_metadata(name="gsw", version="3.3.1")
    sdist_metadata = recipe._get_sdist_metadata(pypi_metadata["sdist_url"], "gsw")
    merged_data = PyPi._merge_pypi_sdist_metadata(pypi_metadata, sdist_metadata)
    assert merged_data["compilers"] == ["c"]
    assert sorted(merged_data["setup_requires"]) == sorted(["numpy"])


def test_update_requirements_with_pin():
    req = {
        "build": ["<{ compiler('c') }}"],
        "host": ["python", "numpy"],
        "run": ["python", "numpy"],
    }
    PyPi._update_requirements_with_pin(req)
    assert req == {
        "build": ["<{ compiler('c') }}"],
        "host": ["python", "numpy"],
        "run": ["python", "<{ pin_compatible('numpy') }}"],
    }


def test_get_compilers():
    assert PyPi._get_compilers(["pybind11"], {}) == ["cxx"]
    assert PyPi._get_compilers(["cython"], {}) == ["c"]
    assert sorted(PyPi._get_compilers(["pybind11", "cython"], {})) == sorted(
        ["cxx", "c"]
    )
    assert sorted(PyPi._get_compilers(["pybind11"], {"compilers": ["c"]})) == sorted(
        ["cxx", "c"]
    )


def test_get_entry_points_from_sdist():
    assert PyPi._get_entry_points_from_sdist({}) == []
    assert PyPi._get_entry_points_from_sdist(
        {"entry_points": {"console_scripts": ["console_scripts=entrypoints"]}}
    ) == ["console_scripts=entrypoints"]
    assert PyPi._get_entry_points_from_sdist(
        {"entry_points": {"gui_scripts": ["gui_scripts=entrypoints"]}}
    ) == ["gui_scripts=entrypoints"]

    assert sorted(
        PyPi._get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": ["gui_scripts=entrypoints"],
                    "console_scripts": ["console_scripts=entrypoints"],
                }
            }
        )
    ) == sorted(["gui_scripts=entrypoints", "console_scripts=entrypoints"])
    assert sorted(
        PyPi._get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": None,
                    "console_scripts": "console_scripts=entrypoints",
                }
            }
        )
    ) == sorted(["console_scripts=entrypoints"])
    assert sorted(
        PyPi._get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": None,
                    "console_scripts": "console_scripts=entrypoints\nfoo=bar.main",
                }
            }
        )
    ) == sorted(["console_scripts=entrypoints", "foo=bar.main"])
    assert sorted(
        PyPi._get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": "gui_scripts=entrypoints",
                    "console_scripts": None,
                }
            }
        )
    ) == sorted(["gui_scripts=entrypoints"])


@pytest.mark.parametrize(
    "name", ["hypothesis", "https://github.com/HypothesisWorks/hypothesis"]
)
def test_build_noarch_skip(name):
    recipe = PyPi(name=name, version="5.5.2")
    assert recipe["build"]["noarch"].values[0] == "python"
    assert not recipe["build"]["skip"].values


def test_run_requirements_sdist():
    recipe = PyPi(name="botocore", version="1.14.17")
    assert sorted(recipe["requirements"]["run"]) == sorted(
        [
            "docutils >=0.10,<0.16",
            "jmespath >=0.7.1,<1.0.0",
            "python",
            "python-dateutil >=2.1,<3.0.0",
            "urllib3 >=1.20,<1.26",
        ]
    )


def test_format_host_requirements():
    assert sorted(
        PyPi._format_dependencies(["setuptools>=40.0", "pkg2"], "pkg1")
    ) == sorted(["setuptools >=40.0", "pkg2"])
    assert sorted(
        PyPi._format_dependencies(["setuptools>=40.0", "pkg2"], "pkg2")
    ) == sorted(["setuptools >=40.0"])
    assert sorted(PyPi._format_dependencies(["setuptools >= 40.0"], "pkg")) == sorted(
        ["setuptools >=40.0"]
    )
    assert sorted(
        PyPi._format_dependencies(["setuptools_scm [toml] >=3.4.1"], "pkg")
    ) == sorted(["setuptools_scm >=3.4.1"])


def test_download_pkg_sdist(pkg_pytest):
    with open(pkg_pytest, "rb") as pkg_file:
        content = pkg_file.read()
        pkg_sha256 = hashlib.sha256(content).hexdigest()
    assert (
        pkg_sha256 == "0d5fe9189a148acc3c3eb2ac8e1ac0742cb7618c084f3d228baaec0c254b318d"
    )
    setup_cfg = PyPi._get_setup_cfg(os.path.dirname(pkg_pytest))
    assert setup_cfg["name"] == "pytest"
    assert setup_cfg["python_requires"] == ">=3.5"
    assert setup_cfg["entry_points"] == {
        "console_scripts": ["pytest=pytest:main", "py.test=pytest:main"]
    }


def test_ciso_recipe():
    recipe = PyPi(name="ciso", version="0.1.0")
    assert sorted(recipe["requirements"]["host"]) == sorted(
        ["cython", "numpy", "pip", "python"]
    )
    assert sorted(recipe["requirements"]["run"]) == sorted(
        ["cython", "python", "<{ pin_compatible('numpy') }}"]
    )
    assert recipe["test"]["commands"] == "pip check"
    assert recipe["test"]["requires"] == "pip"
    assert recipe["test"]["imports"] == "ciso"


@pytest.mark.serial
@pytest.mark.xfail(
    condition=(sys.platform.startswith("win")),
    reason="Test failing on windows platform",
)
def test_pymc_recipe_fortran():
    recipe = PyPi(name="pymc", version="2.3.6")
    assert sorted(recipe["requirements"]["build"]) == sorted(
        ["<{ compiler('c') }}", "<{ compiler('fortran') }}"]
    )
    assert sorted(recipe["requirements"]["host"]) == sorted(["numpy", "python", "pip"])
    assert sorted(recipe["requirements"]["run"]) == sorted(
        ["<{ pin_compatible('numpy') }}", "python"]
    )
    assert not recipe["build"]["noarch"]


@pytest.mark.github
@pytest.mark.parametrize("name", ["pytest", "https://github.com/pytest-dev/pytest"])
def test_pytest_recipe_entry_points(name):
    recipe = PyPi(name=name, version="5.3.5")
    assert sorted(recipe["build"]["entry_points"]) == sorted(
        ["pytest=pytest:main", "py.test=pytest:main"]
    )
    assert recipe["about"]["license"] == "MIT"
    assert recipe["about"]["license_file"] == "LICENSE"
    assert recipe["build"]["skip"].values[0].value
    assert recipe["build"]["skip"].values[0].selector == "py2k"
    assert not recipe["build"]["noarch"]
    assert sorted(recipe["test"]["commands"].values) == sorted(
        ["py.test --help", "pytest --help", "pip check"]
    )


def test_cythongsl_recipe_build():
    recipe = PyPi(name="cythongsl", version="0.2.2")
    assert recipe["requirements"]["build"] == "<{ compiler('c') }}"
    assert recipe["requirements"]["host"] == ["cython >=0.16", "pip", "python"]
    assert not recipe["build"]["noarch"]


@pytest.mark.github
@pytest.mark.parametrize("name", ["requests", "https://github.com/psf/requests"])
def test_requests_recipe_extra_deps(capsys, name):
    CLIConfig().stdout = True
    recipe = PyPi(name=name, version="2.22.0")
    captured_stdout = capsys.readouterr()
    assert "win-inet-pton" not in recipe["requirements"]["run"]
    assert recipe["build"]["noarch"]
    assert not recipe["build"]["skip"]
    assert f"{Fore.GREEN}{Style.BRIGHT}python" in captured_stdout.out


def test_zipp_recipe_tags_on_deps():
    recipe = PyPi(name="zipp", version="3.0.0")
    assert recipe["build"]["noarch"]
    assert recipe["requirements"]["host"] == [
        "pip",
        "python >=3.6",
        "setuptools-scm >=3.4.1",
    ]


def test_generic_py_ver_to():
    assert PyPi._generic_py_ver_to({"requires_python": ">=3.5, <3.8"}) == ">=3.5,<3.8"


def test_botocore_recipe_license_name():
    recipe = PyPi(name="botocore", version="1.15.8")
    assert recipe["about"]["license"] == "Apache-2.0"


def test_ipytest_recipe_license():
    recipe = PyPi(name="ipytest", version="0.8.0")
    assert recipe["about"]["license"] == "MIT"


def test_get_test_entry_points():
    assert PyPi._get_test_entry_points("grayskull = grayskull.__main__:main") == [
        "grayskull --help"
    ]
    assert PyPi._get_test_entry_points(
        ["pytest = py.test:main", "py.test = py.test:main"]
    ) == ["pytest --help", "py.test --help"]


def test_importlib_metadata_two_setuptools_scm():
    recipe = PyPi(name="importlib-metadata", version="1.5.0")
    assert "setuptools-scm" in recipe["requirements"]["host"]
    assert "setuptools_scm" not in recipe["requirements"]["host"]
    assert recipe["about"]["license"] == "Apache-2.0"


def test_keyring_host_appearing_twice():
    recipe = PyPi(name="keyring", version="21.1.1")
    assert "importlib-metadata" in recipe["requirements"]["run"]
    assert "importlib_metadata" not in recipe["requirements"]["run"]


def test_python_requires_setup_py():
    recipe = PyPi(name="pygments", version="2.6.1")
    assert "noarch" in recipe["build"]
    assert "python >=3.5" in recipe["requirements"]["host"]
    assert "python >=3.5" in recipe["requirements"]["run"]


@pytest.mark.skipif(sys.platform.startswith("darwin"), reason="Skipping OSX test")
def test_django_rest_framework_xml_license():
    recipe = PyPi(name="djangorestframework-xml", version="1.4.0")
    assert recipe["about"]["license"] == "BSD-3-Clause"
    assert recipe["about"]["license_file"] == "LICENSE"
    assert recipe["test"]["imports"][0].value == "rest_framework_xml"


def test_get_test_imports():
    assert PyPi._get_test_imports({"packages": ["pkg", "pkg.mod1", "pkg.mod2"]}) == [
        "pkg",
        "pkg.mod1",
    ]
    assert PyPi._get_test_imports({"packages": None}, default="pkg-mod") == ["pkg_mod"]
    assert PyPi._get_test_imports({"packages": "pkg"}, default="pkg-mod") == ["pkg"]


def test_nbdime_license_type():
    recipe = PyPi(name="nbdime", version="2.0.0")
    assert recipe["about"]["license"] == "BSD-3-Clause"
    assert "setupbase" not in recipe["requirements"]["host"]


def test_normalize_pkg_name():
    assert PyPi._normalize_pkg_name("mypy-extensions") == "mypy_extensions"
    assert PyPi._normalize_pkg_name("mypy_extensions") == "mypy_extensions"
    assert PyPi._normalize_pkg_name("pytest") == "pytest"


def test_mypy_deps_normalization_and_entry_points():
    recipe = PyPi(name="mypy", version="0.770")
    assert "mypy_extensions >=0.4.3,<0.5.0" in recipe["requirements"]["run"]
    assert "mypy-extensions >=0.4.3,<0.5.0" not in recipe["requirements"]["run"]
    assert "typed-ast >=1.4.0,<1.5.0" in recipe["requirements"]["run"]
    assert "typed_ast <1.5.0,>=1.4.0" not in recipe["requirements"]["run"]
    assert "typing-extensions >=3.7.4" in recipe["requirements"]["run"]
    assert "typing_extensions >=3.7.4" not in recipe["requirements"]["run"]

    assert recipe["build"]["entry_points"].values == [
        "mypy=mypy.__main__:console_entry",
        "stubgen=mypy.stubgen:main",
        "stubtest=mypy.stubtest:main",
        "dmypy=mypy.dmypy.client:console_entry",
    ]


@pytest.mark.skipif(
    condition=sys.platform.startswith("win"), reason="Skipping test for win"
)
def test_panel_entry_points(tmpdir):
    recipe = PyPi(name="panel", version="0.9.1")
    recipe.generate_recipe(folder_path=str(tmpdir))
    recipe_path = str(tmpdir / "panel" / "meta.yaml")
    with open(recipe_path, "r") as f:
        content = f.read()
    assert "- panel = panel.cli:main" in content


def test_deps_comments():
    recipe = PyPi(name="kubernetes_asyncio", version="11.2.0")
    assert recipe["requirements"]["run"] == [
        "aiohttp >=2.3.10,<4.0.0",
        "certifi >=14.05.14",
        "python",
        "python-dateutil >=2.5.3",
        "pyyaml >=3.12",
        "setuptools >=21.0.0",
        "six >=1.9.0",
        "urllib3 >=1.24.2",
    ]


@pytest.mark.github
@pytest.mark.parametrize("name", ["respx", "https://github.com/lundberg/respx"])
def test_keep_filename_license(name):
    recipe = PyPi(name=name, version="0.10.1")
    assert recipe["about"]["license_file"] == "LICENSE.md"


def test_platform_system_selector():
    assert (
        PyPi._parse_extra_metadata_to_selector("platform_system", "==", "Windows")
        == "win"
    )
    assert (
        PyPi._parse_extra_metadata_to_selector("platform_system", "!=", "Windows")
        == "not win"
    )


def test_tzdata_without_setup_py():
    recipe = PyPi(name="tzdata", version="2020.1")
    assert recipe["build"]["noarch"] == "python"
    assert recipe["about"]["home"] == "https://github.com/python/tzdata"


def test_multiples_exit_setup():
    """Bug fix #146"""
    recipe = PyPi(name="pyproj", version="2.6.1")
    assert recipe


def test_sequence_inside_another_in_dependencies():
    recipe = PyPi(name="unittest2", version="1.1.0")
    assert recipe["requirements"]["host"] == [
        "argparse",
        "pip",
        "python",
        "six >=1.4",
        "traceback2",
    ]
    assert recipe["requirements"]["run"] == [
        "argparse",
        "python",
        "six >=1.4",
        "traceback2",
    ]


def test_recipe_with_just_py_modules():
    recipe = PyPi(name="python-markdown-math", version="0.7")
    assert recipe["test"]["imports"] == "mdx_math"


def test_recipe_extension():
    recipe = PyPi(name="azure-identity", version="1.3.1")
    assert (
        recipe["source"]["url"][0].value
        == "https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/"
        "azure-identity-{{ version }}.zip"
    )


def test_get_url_filename():
    assert PyPi._get_url_filename({}) == "{{ name }}-{{ version }}.tar.gz"
    assert PyPi._get_url_filename({}, "default") == "default"
    assert (
        PyPi._get_url_filename({"urls": [{"packagetype": "nothing"}]})
        == "{{ name }}-{{ version }}.tar.gz"
    )
    assert (
        PyPi._get_url_filename({"urls": [{"packagetype": "nothing"}]}, "default")
        == "default"
    )
    assert (
        PyPi._get_url_filename(
            {
                "info": {"version": "1.2.3"},
                "urls": [{"packagetype": "sdist", "filename": "foo_file-1.2.3.zip"}],
            }
        )
        == "foo_file-{{ version }}.zip"
    )


def test_clean_deps_for_conda_forge():
    assert clean_deps_for_conda_forge(["deps1", "deps2  # [py34]"]) == ["deps1"]
    assert clean_deps_for_conda_forge(["deps1", "deps2  # [py<34]"]) == ["deps1"]
    assert clean_deps_for_conda_forge(["deps1", "deps2  # [py<38]"]) == [
        "deps1",
        "deps2  # [py<38]",
    ]


def test_empty_entry_points():
    recipe = PyPi(name="modulegraph", version="0.18")
    assert recipe["build"]["entry_points"] == "modulegraph = modulegraph.__main__:main"


def test_noarch_metadata():
    recipe = PyPi(name="policy_sentry", version="0.11.16")
    assert recipe["build"]["noarch"] == "python"


def test_arch_metadata():
    recipe = PyPi(name="remove_dagmc_tags", version="0.0.5")
    assert "noarch" not in recipe["build"]
