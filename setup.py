from setuptools import setup, find_packages

setup(
    name="ztp_agent",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "cmd2>=2.0.0",
        "prompt_toolkit>=3.0.0",
        "paramiko>=2.7.0",
        "smolagents>=0.1.0",
        "openai>=1.0.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "ztp-agent=ztp_agent.main:main",
        ],
    },
    author="John",
    author_email="john@example.com",
    description="Zero-Touch Provisioning agent for RUCKUS devices",
    keywords="ztp, network, automation, ruckus",
    python_requires=">=3.8",
)
