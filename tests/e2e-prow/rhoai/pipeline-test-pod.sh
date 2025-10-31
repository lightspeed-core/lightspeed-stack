#!/bin/bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

oc apply -f "$BASE_DIR/manifests/test-pod/spin-up.yaml"
