#!/bin/bash
set -e

echo "Installing Lambda dependencies..."
pip install -r lambdas/requirements.txt -t lambdas/ --quiet --upgrade

echo "Deploying CDK stack..."
cdk deploy --require-approval never
