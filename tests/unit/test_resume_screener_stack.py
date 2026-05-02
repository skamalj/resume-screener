import aws_cdk as core
import aws_cdk.assertions as assertions

from resume_screener.resume_screener_stack import ResumeScreenerStack

# example tests. To run these tests, uncomment this file along with the example
# resource in resume_screener/resume_screener_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = ResumeScreenerStack(app, "resume-screener")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
