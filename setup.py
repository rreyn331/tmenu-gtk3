from setuptools import setup

setup(
    name="tmenu",
    version="2026.03.19",
    packages=["tmenu"],
    package_data={
        "tmenu": ["data/*.css"]
    },
    include_package_data=False
)