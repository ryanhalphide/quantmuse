import os
import shutil
import subprocess
from pathlib import Path

from setuptools import setup, find_packages, Extension
from setuptools.command.build_ext import build_ext as _build_ext

REPO_ROOT = Path(__file__).parent.resolve()

# The C++ engine (backend/) is an optional native extension -- opt-in via
# QUANTMUSE_BUILD_CPP=1 so a plain `pip install -e .` never needs a C++
# toolchain, CMake, pybind11, spdlog, nlohmann-json, or Boost.
#
#   QUANTMUSE_BUILD_CPP=1 pip install -e ".[cpp]"
#
# See USAGE.md Sec.17 for the full walkthrough (including the manual
# cmake/ctest commands this wraps).
BUILD_CPP = os.environ.get("QUANTMUSE_BUILD_CPP", "").lower() in ("1", "true", "yes")


class CMakeBuild(_build_ext):
    """Builds the quantmuse_engine pybind11 extension via CMake (backend/)
    and drops the compiled module at the repo root, where it's importable
    from an editable install without depending on setuptools' compiled-
    extension placement for editable installs.
    """

    def run(self):
        import pybind11  # build-time only; not a runtime dependency

        backend_dir = REPO_ROOT / "backend"
        build_dir = backend_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)

        subprocess.check_call([
            "cmake", "-B", str(build_dir), str(backend_dir),
            "-DBUILD_PYTHON_MODULE=ON",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-Dpybind11_DIR={pybind11.get_cmake_dir()}",
        ])
        subprocess.check_call([
            "cmake", "--build", str(build_dir), "--target", "quantmuse_engine",
        ])

        built = next(build_dir.glob("quantmuse_engine*.so"), None) \
            or next(build_dir.glob("quantmuse_engine*.pyd"), None)
        if built is None:
            raise RuntimeError(
                f"quantmuse_engine build did not produce an extension module in {build_dir}"
            )
        shutil.copyfile(built, REPO_ROOT / built.name)
        print(f"quantmuse_engine built and copied to {REPO_ROOT / built.name}")


setup(
    name="data_service",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pandas',
        'numpy',
        'python-binance>=1.0.0',
        'websocket-client>=1.0.0',
        'websockets>=10.0',
        'aiohttp>=3.8.0',
        'alpha_vantage',
        'fastapi',
        'uvicorn',
        'redis',
        'requests',
        'textblob',
        'openpyxl',
        # factors/backtest import matplotlib+seaborn and strategies imports
        # scipy at module load, so they must be base deps
        'matplotlib>=3.5.0',
        'seaborn>=0.11.0',
        'scipy'
    ],
    ext_modules=[Extension("quantmuse_engine", sources=[])] if BUILD_CPP else [],
    cmdclass={"build_ext": CMakeBuild} if BUILD_CPP else {},
    extras_require={
        'test': [
            'pytest',
            'pytest-cov',
            'pytest-asyncio'
        ],
        'ai': [
            'openai',
            'langchain',
            'langchain-openai',
            'langchain-community',
            'transformers',
            'torch',
            'sentence-transformers',
            'accelerate',
            'spacy',
            'nltk',
            'textblob',
            'scikit-learn',
            'wordcloud'
        ],
        'visualization': [
            'matplotlib>=3.5.0',
            'seaborn>=0.11.0',
            'plotly>=5.0.0',
            'streamlit>=1.20.0',
            'kaleido>=0.2.1'  # 用于Plotly静态图片导出
        ],
        'realtime': [
            'websockets>=10.0',
            'aiohttp>=3.8.0',
            'asyncio-mqtt>=0.11.0',
            'redis>=4.0.0'
        ],
        'web': [
            'fastapi',
            'uvicorn[standard]',
            'jinja2',
            'aiofiles'
        ],
        'kalshi': [
            'requests',
            'pandas',
            'cryptography>=41.0.0'  # required to sign authenticated trading requests
        ],
        'cpp': [
            'pybind11>=2.10'
        ]
    }
)
