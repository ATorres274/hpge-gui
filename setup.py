from setuptools import find_packages, setup

setup(
    name="pyHPGeGui",
    version="0.1.0",
    description="PyROOT GUI browser for HPGe analysis",
    py_modules=["main"],
    packages=find_packages(),
    entry_points={"console_scripts": ["pyHPGeGui=main:main"]},
    python_requires=">=3.10",
)
