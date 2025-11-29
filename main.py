import boto3
import configparser
import sys
import os


"""
    AWS SETUP
"""
def validateAWSCredentials():
    try:
        print('- Validating the AWS credentials')

        aws_access_key_id = None
        aws_secret_access_key = None
        aws_session_token = None
        is_not_valid = True

        credentials_path = os.path.expanduser('~/.aws/credentials')
        config = configparser.ConfigParser()

        if os.path.exists(credentials_path):
            config.read(credentials_path)
            if 'default' in config:
                aws_access_key_id = config['default'].get('aws_access_key_id')
                aws_secret_access_key = config['default'].get('aws_secret_access_key')
                aws_session_token = config['default'].get('aws_session_token')

        if not aws_access_key_id or not aws_secret_access_key:
            aws_access_key_id, aws_secret_access_key, aws_session_token = getAWSCredentials()

        while is_not_valid:
            try:
                sts = boto3.client(
                    'sts',
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key,
                    aws_session_token=aws_session_token
                )

                sts.get_caller_identity()
                is_not_valid = False

            except Exception:
                print('- credential verification failed\n')
                aws_access_key_id, aws_secret_access_key, aws_session_token = getAWSCredentials()

        os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
        if aws_session_token:
            os.environ['AWS_SESSION_TOKEN'] = aws_session_token

        print('- AWS credentials verified')

    except Exception as e:
        print(f'Failed to validate user\'s credentials: {e}')
        sys.exit(1)


def getAWSCredentials() -> tuple[str, str, str | None]:
    try:
        print('- Enter the following required variables to login')
        aws_access_key_id = input('→ AWS Access Key Id: ')
        aws_secret_access_key = input('→ AWS Secret Access Key: ')
        aws_session_token = input('→ AWS Session Token (press enter if none): ')

        return aws_access_key_id, aws_secret_access_key, aws_session_token
    
    except Exception as e:
        print(f'Failed to get user\'s input credentials: {e}')
        sys.exit(1)


def setBoto3Clients():
    try:
        print('- Starting setting up the boto3 clients')

        global EC2_CLIENT, S3_CLIENT

        EC2_CLIENT = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )

        S3_CLIENT = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )

        print('- finished setting up the boto3 clients')

    except Exception as e:
        print(f'Failed to set Boto3\'s clients: {e}')
        sys.exit(1)


"""
    Utils Methods
"""
def read_user_data(filename: str) -> str:
    try:
        filepath = os.path.join('user-data', filename)
        with open(filepath, 'r') as f:
            return f.read()
        
    except Exception:
        print(f'- error reading user data file {filepath}')
        sys.exit(1)


"""
    AWS Entities
"""
def createVPC(cidr_block='10.0.0.0/16', vpc_name='log8415e-vpc'):
    try:
        print(f'- Creating VPC: {vpc_name} with CIDR: {cidr_block}')
        
        vpc_response = EC2_CLIENT.create_vpc(
            CidrBlock=cidr_block,
            TagSpecifications=[
                {
                    'ResourceType': 'vpc',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': vpc_name
                        }
                    ]
                }
            ]
        )
        
        vpc_id = vpc_response['Vpc']['VpcId']
        
        EC2_CLIENT.modify_vpc_attribute(
            VpcId=vpc_id,
            EnableDnsHostnames={'Value': True}
        )
        
        EC2_CLIENT.modify_vpc_attribute(
            VpcId=vpc_id,
            EnableDnsSupport={'Value': True}
        )
        
        print(f'- VPC created successfully with ID: {vpc_id}')
        
        return vpc_id
        
    except Exception as e:
        print(f'- Failed to create VPC {vpc_id}: {e}')
        sys.exit(1)


def createSubnet(vpc_id, cidr_block, availability_zone, subnet_name, is_public=False):
    try:
        print(f'- Creating Subnet: {subnet_name} in {availability_zone}')
        
        subnet_response = EC2_CLIENT.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr_block,
            AvailabilityZone=availability_zone,
            TagSpecifications=[
                {
                    'ResourceType': 'subnet',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': subnet_name
                        }
                    ]
                }
            ]
        )
        
        subnet_id = subnet_response['Subnet']['SubnetId']
        
        if is_public:
            EC2_CLIENT.modify_subnet_attribute(
                SubnetId=subnet_id,
                MapPublicIpOnLaunch={'Value': True}
            )
            print(f'- Public Subnet created with ID: {subnet_id}')
        else:
            print(f'- Private Subnet created with ID: {subnet_id}')
        
        return subnet_id
        
    except Exception as e:
        print(f'- Failed to create subnet: {e}')
        sys.exit(1)


def createInternetGateway(vpc_id, igw_name='log8415e-igw'):
    try:
        print(f'- Creating Internet Gateway: {igw_name}')
        
        igw_response = EC2_CLIENT.create_internet_gateway(
            TagSpecifications=[
                {
                    'ResourceType': 'internet-gateway',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': igw_name
                        }
                    ]
                }
            ]
        )
        
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        
        EC2_CLIENT.attach_internet_gateway(
            InternetGatewayId=igw_id,
            VpcId=vpc_id
        )
        
        print(f'- Internet Gateway created and attached: {igw_id}')
        
        return igw_id
        
    except Exception as e:
        print(f'- Failed to create internet gateway: {e}')
        sys.exit(1)


def createSecurityGroup(vpc_id, sg_name='log8415e-sg', sg_description='Security group for final assignment'):
    try:
        pass
    except Exception as e:
        print(f'- Failed to create security group: {e}')
        sys.exit(1)


"""
    MySQL Standalone and Sakila
"""
def create_worker_instances(nbrInstances: int, vpcId: str, subnetId: str,) -> list[str]:
    print('- creating new worker instances')
    instancesId = []

    ingress = []
    egress = []
    userData = read_user_data('worker.tpl')
    sgId = createSecurityGroup(vpcId= vpcId, sgName='sg-workers', ingressRules= ingress, egressRules=egress)
    try:
        response = EC2_CLIENT.run_instances(
            ImageId= 'ami-0157af9aea2eef346',
            InstanceType= 't2.micro',
            SubnetId= subnetId,
            SecurityGroupIds= [sgId],
            MinCount= nbrInstances,
            MaxCount= nbrInstances,
            UserData= userData,
            TagSpecifications= [
                {
                    'ResourceType': 'instance',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': f'worker-{i+1}'
                        } for i in range(nbrInstances)
                    ]
                }
            ]
        )

        instancesId = [instance['InstanceId'] for instance in response['Instances']]
        print(f'- created {nbrInstances} worker instances successfully')
        return instancesId

    except Exception:
        print('- failed to create worker instances')
        sys.exit(1)


def create_manager_instances(nbrInstances: int, vpcId: str, subnetId: str,) -> list[str]:
    print('- creating new manager instances')
    instancesId = []

    ingress = []
    egress = []
    userData = read_user_data('manager.tpl')
    sgId = create_security_group(sgName='sg-managers', vpcId= vpcId, ingressRules= ingress, egressRules=egress)
    try:
        response = EC2_CLIENT.run_instances(
            ImageId= 'ami-0157af9aea2eef346',
            InstanceType= 't2.micro',
            SubnetId= subnetId,
            SecurityGroupIds= [sgId],
            MinCount= nbrInstances,
            MaxCount= nbrInstances,
            UserData= userData,
            TagSpecifications= [
                {
                    'ResourceType': 'instance',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': f'manager-{i+1}'
                        } for i in range(nbrInstances)
                    ]
                }
            ]
        )

        instancesId = [instance['InstanceId'] for instance in response['Instances']]
        print(f'- created {nbrInstances} manager instances successfully')
        return instancesId

    except Exception:
        print('- failed to create manager instances')
        sys.exit(1)


"""
    Proxy
"""


"""
    Gatekeeper
"""


"""
    Benchmark
"""


def main():
    print('*'*16 + ' AWS Boto3 script ' + '*'*16)
    validateAWSCredentials()
    setBoto3Clients()
    print('*'*50 + '\n')


if __name__ == '__main__':
    main()