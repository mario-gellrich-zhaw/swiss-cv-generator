from setuptools import setup, find_packages

setup(
    name='swiss_cv_generator',
    version='0.1.0',
    description='Swiss CV Generator (local package for development)',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    include_package_data=True,
    install_requires=[],
)
