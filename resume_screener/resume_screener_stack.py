from aws_cdk import (
    Duration,
    Stack,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_sns as sns,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    RemovalPolicy,
    aws_lambda_event_sources as lambda_events,
)
from constructs import Construct

class ResumeScreenerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Import IAM Role
        app_role = iam.Role.from_role_arn(
            self, "AppRole",
            role_arn="arn:aws:iam::719030485523:role/resume-app-role",
            mutable=False
        )

        # 2. S3 Bucket for Emails
        email_bucket = s3.Bucket(
            self, "IncomingEmailsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # 3. Import SNS Topic
        topic = sns.Topic.from_topic_arn(
            self, "ResumeScreenerTopic",
            topic_arn="arn:aws:sns:ap-south-1:719030485523:resume-screener-topic"
        )

        # S3 does not trigger SNS directly; SES handles triggering SNS and S3 independently.

        # 4. Lambda Functions
        # Dependencies must be pre-installed in lambdas/ before deploy:
        #   pip install -r lambdas/requirements.txt -t lambdas/
        lambda_code = lambda_.Code.from_asset("lambdas")

        def create_lambda(id: str, handler: str, timeout_secs: int = 30, memory_size: int = 256):
            return lambda_.Function(
                self, id,
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler=f"{handler}.handler",
                code=lambda_code,
                timeout=Duration.seconds(timeout_secs),
                memory_size=memory_size,
                environment={
                    "EMAIL_BUCKET": email_bucket.bucket_name
                }
            )

        parser_lambda = create_lambda("ParserLambda", "parser", timeout_secs=120, memory_size=512)
        analyzer_lambda = create_lambda("AnalyzerLambda", "analyzer", timeout_secs=180, memory_size=512)
        responder_lambda = create_lambda("ResponderLambda", "responder", timeout_secs=120, memory_size=512)
        error_lambda = create_lambda("ErrorLambda", "error_handler", timeout_secs=30)

        # Grant specific permissions to the auto-generated Lambda roles
        email_bucket.grant_read_write(parser_lambda)  # reads raw email, writes extracted docs
        email_bucket.grant_read(error_lambda)
        email_bucket.grant_read_write(analyzer_lambda)  # reads extracted docs from S3

        ssm_openai_key_arn = "arn:aws:ssm:ap-south-1:719030485523:parameter/irdai/openai-api-key"

        parser_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[ssm_openai_key_arn]
            )
        )

        analyzer_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[ssm_openai_key_arn]
            )
        )
        
        responder_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendRawEmail", "ses:SendEmail"],
                resources=["*"]
            )
        )
        
        error_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendRawEmail", "ses:SendEmail"],
                resources=["*"]
            )
        )

        # 5. Step Functions Workflow
        parse_task = tasks.LambdaInvoke(
            self, "Extract and Parse Documents",
            lambda_function=parser_lambda,
            output_path="$.Payload"
        )
        
        analyze_task = tasks.LambdaInvoke(
            self, "Analyze Fitment with Gemini",
            lambda_function=analyzer_lambda,
            output_path="$.Payload"
        )
        
        respond_task = tasks.LambdaInvoke(
            self, "Generate PDFs and Send Response",
            lambda_function=responder_lambda,
            output_path="$.Payload"
        )
        
        error_task = tasks.LambdaInvoke(
            self, "Send Error Notification",
            lambda_function=error_lambda,
            output_path="$.Payload"
        )

        # Catch errors and route to error_task
        parse_task.add_catch(error_task, result_path="$.error_info")
        analyze_task.add_catch(error_task, result_path="$.error_info")
        respond_task.add_catch(error_task, result_path="$.error_info")

        definition = parse_task.next(analyze_task).next(respond_task)

        state_machine = sfn.StateMachine(
            self, "ResumeScreenerStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition)
        )

        # 6. Starter Lambda (Triggered by SNS, starts Step Functions)
        starter_lambda = create_lambda("StarterLambda", "starter", timeout_secs=30)
        starter_lambda.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

        # Grant StarterLambda permission to start Step Functions executions
        state_machine.grant_start_execution(starter_lambda)

        starter_lambda.add_event_source(
            lambda_events.SnsEventSource(topic)
        )
