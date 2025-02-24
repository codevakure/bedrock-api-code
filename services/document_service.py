from fastapi import HTTPException, UploadFile, Response
from typing import Optional, Dict, Any
from config.aws_config import s3_client, bucket
from botocore.exceptions import ClientError
from uuid import uuid4
from io import BytesIO
from datetime import datetime

class DocumentService:
    @staticmethod
    async def list_documents(file_type: Optional[str] = None) -> Dict[str, Any]:
        """List all documents in S3 bucket with optional filtering"""
        try:
            # Get documents from S3
            s3_response = s3_client.list_objects_v2(Bucket=bucket)
            
            documents = []
            if 'Contents' in s3_response:
                for item in s3_response['Contents']:
                    key = item['Key']
                    file_extension = key.split('.')[-1].lower() if '.' in key else ''
                    
                    # Get metadata for the file
                    original_filename = None
                    try:
                        metadata_response = s3_client.head_object(Bucket=bucket, Key=key)
                        original_filename = metadata_response.get('Metadata', {}).get('original_filename')
                    except ClientError:
                        pass
                    
                    # Determine content type based on extension
                    content_type_mapping = {
                        'pdf': 'application/pdf',
                        'doc': 'application/msword',
                        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'txt': 'text/plain'
                    }
                    content_type = content_type_mapping.get(file_extension, 'application/octet-stream')
                    
                    # Apply file type filter if specified
                    if file_type and file_extension != file_type.lower():
                        continue
                    
                    doc_info = {
                        'key': key,
                        'size': item['Size'],
                        'last_modified': item['LastModified'].isoformat(),
                        'content_type': content_type,
                        'file_extension': file_extension,
                        'original_filename': original_filename
                    }
                    documents.append(doc_info)

            return {
                'documents': documents,
                'total_count': len(documents)
            }

        except Exception as e:
            error_message = f"Error listing documents: {str(e)}"
            print(error_message)
            raise HTTPException(status_code=500, detail=error_message)

    @staticmethod
    async def get_document(document_key: str):
        """Get document from S3"""
        try:
            response = s3_client.get_object(Bucket=bucket, Key=document_key)
            content = response['Body'].read()
            
            return {
                'content': content,
                'content_type': response['ContentType'],
                'filename': document_key
            }

        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="Document not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def get_document_details(document_key: str) -> Dict[str, Any]:
        """Get document metadata from S3"""
        try:
            response = s3_client.head_object(Bucket=bucket, Key=document_key)
            
            return {
                'key': document_key,
                'size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'content_type': response.get('ContentType', 'application/octet-stream'),
                'metadata': response.get('Metadata', {})
            }

        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="Document not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def upload_document(file: UploadFile) -> Dict[str, str]:
        """Upload document to S3"""
        try:
            if not file.filename:
                raise HTTPException(status_code=400, detail="No file provided")
            
            # Generate unique filename
            file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
            unique_filename = f"{str(uuid4())}.{file_extension}"
            
            # Read file content
            content = await file.read()
            
            # Upload to S3
            s3_client.upload_fileobj(
                BytesIO(content),
                bucket,
                unique_filename,
                ExtraArgs={
                    'ContentType': file.content_type,
                    'Metadata': {
                        'original_filename': file.filename
                    }
                }
            )

            return {
                'message': 'File uploaded successfully',
                'filename': unique_filename,
                'original_filename': file.filename
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def delete_document(document_key: str) -> Dict[str, str]:
        """Delete document from S3"""
        try:
            s3_client.delete_object(
                Bucket=bucket,
                Key=document_key
            )
            
            return {
                'message': f'Document {document_key} deleted successfully',
                'deleted_key': document_key
            }
            
        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="Document not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))