import os.path
from setuptools import setup, find_packages

HERE = os.path.abspath(os.path.dirname(__file__))

# The text of the README file
with open(os.path.join(HERE, "README.rst")) as fid:
    README = fid.read()


setup(
    name="sirius-sdk",
    version="1.0.16",
    description="SDK for developing Smart-Contracts in Self-sovereign-identity world.",
    long_description=README,
    long_description_content_type="text/x-rst",
    url="https://github.com/Sirius-social/sirius-sdk-python",
    author="Networks Synergy",
    author_email="support@socialsirius.com",
    project_urls={
        'Chat: Telegram': 'https://t.me/sirius_sdk',
        'CI: Travis': 'https://travis-ci.com/github/Sirius-social/sirius-sdk-python/builds',
        'GitHub: issues': 'https://github.com/Sirius-social/sirius-sdk-python/issues',
        'GitHub: repo': 'https://github.com/Sirius-social/sirius-sdk-python',
    },
    license="Apache License",
    maintainer=', '.join(('Pavel Minenkov <minikspb@gmail.com>',)),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
    ],
    packages=find_packages(),
    python_requires='>=3.7',
    include_package_data=True,
    install_requires=[
        'aiohttp==3.6.2',
        'base58==2.0.0',
        'multipledispatch==0.6.0',
        'PyNaCl==1.3.0',
        'pytest==5.4.2',
        'pytest-asyncio==0.12.0',
        'python-dateutil==2.8.1',
        'pytime==0.2.0',
        'semver==2.10.1',
    ]
)
