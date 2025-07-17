#!/usr/bin/env python3

# Copyright © 2022, 2023, 2025 Pavel Tisnovsky
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Scenario list generator."""

# Usage
# python gen_scenario_list.py > docs/scenarios_list.md

import os

# repository URL
REPO_URL = "https://github.com/lightspeed-core/lightspeed-stack/"

# URL prefix to create links to feature files
FEATURES_URL_PREFIX = f"{REPO_URL}blob/main/tests/e2e/features"

# list of prefixes for scenarios or scenario outlines
PREFIXES = ("Scenario: ", "Scenario Outline: ")

# sub-directory where feature files are stored
FEATURE_DIRECTORY = "features"

# generate page header
print("---")
print("layout: page")
print("nav_order: 3")
print("---")
print()
print("# List of scenarios")
print()

# generage list of scenarios

# files within one subdirectory needs to be sorted so the
# resulting scenario list will have stable structure across versions
files = sorted(os.listdir(FEATURE_DIRECTORY))
for filename in files:
    # grep all .feature files
    if filename.endswith(".feature"):
        # feature file header
        print(f"## [`{filename}`]({FEATURES_URL_PREFIX}/{filename})\n")
        with open(
            os.path.join(FEATURE_DIRECTORY, filename), "r", encoding="utf-8"
        ) as fin:
            for line in fin.readlines():
                line = line.strip()
                # process all scenarios and scenario outlines
                for prefix in PREFIXES:
                    if line.startswith(prefix):
                        line = line[len(prefix) :]
                        print(f"* {line}")
        # vertical space between subsections in generated file
        print()
