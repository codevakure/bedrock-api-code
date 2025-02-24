# app/middleware/error_handler.py
from fastapi import Request
from fastapi.responses import JSONResponse
from botocore.exceptions import ClientError

async def aws_error_handler(request: Request, call_next):
    try:
        return await call_next(request)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'ThrottlingException':
            return JSONResponse(
                status_code=429,
                content={
                    'error': 'Rate limit exceeded. Please try again later.',
                    'details': error_message
                }
            )
        elif error_code == 'ValidationException':
            return JSONResponse(
                status_code=400,
                content={
                    'error': 'Invalid request',
                    'details': error_message
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    'error': 'AWS Service Error',
                    'details': str(e)
                }
            )