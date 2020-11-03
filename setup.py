# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2020 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2020: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import setuptools

with open("README.md", "r") as f:
    long_description = f.read()

with open("./version.py", "r", encoding="utf-8") as v:
    for line in v.readlines():
        if line.startswith("__version__"):
            if '"' in line:
                version = line.split('"')[1]
            else:
                version = line.split("'")[1]

setuptools.setup(
    name="chatbot-core",
    version=version,
    author="NeonDaniel",
    author_email="daniel@neon.ai",
    description="Core utilities for Klat chatbots",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/neongeckocom/chatbot-core",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: Apache License 2.0",
        "Operating System :: OS Independent"
    ],
    python_requires='>=3.6',
    entry_points={'console_scripts': ["start-klat-bots=chatbot_core.utils:cli_start_bots",
                                      "stop-klat-bots=chatbot_core.utils:cli_stop_bots",
                                      "debug-klat-bots=chatbot_core.utils:debug_bots"]},
    install_requires=[
        "mycroft-messagebus-client",
        "psutil~=5.7.3"
        "klat-connector @ git+https://github.com/neongeckocom/klat-connector@master#egg=klat-connector>=0.1.0"
    ]
)
