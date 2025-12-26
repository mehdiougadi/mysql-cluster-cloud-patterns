import sys
import os


def delete_ec2_instances(ec2_client, vpc_id):
    try:
        print('- Finding EC2 instances to delete')
        
        response = ec2_client.describe_instances(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']}
            ]
        )
        
        instance_ids = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_ids.append(instance['InstanceId'])
        
        if instance_ids:
            print(f'- Terminating {len(instance_ids)} instances: {instance_ids}')
            ec2_client.terminate_instances(InstanceIds=instance_ids)
            
            print('- Waiting for instances to terminate...')
            waiter = ec2_client.get_waiter('instance_terminated')
            waiter.wait(InstanceIds=instance_ids)
            
            print('- All instances terminated successfully')
        else:
            print('- No instances found to delete')
            
    except Exception as e:
        print(f'- Error deleting EC2 instances: {e}')


def delete_nat_gateways(ec2_client, vpc_id):
    try:
        print('- Finding NAT Gateways to delete')
        
        response = ec2_client.describe_nat_gateways(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'state', 'Values': ['available', 'pending']}
            ]
        )
        
        nat_gateways = response['NatGateways']
        
        if nat_gateways:
            allocation_ids = []
            for nat in nat_gateways:
                for address in nat.get('NatGatewayAddresses', []):
                    if 'AllocationId' in address:
                        allocation_ids.append(address['AllocationId'])
            
            nat_gateway_ids = [nat['NatGatewayId'] for nat in nat_gateways]
            
            print(f'- Deleting {len(nat_gateway_ids)} NAT Gateway(s): {nat_gateway_ids}')
            for nat_id in nat_gateway_ids:
                ec2_client.delete_nat_gateway(NatGatewayId=nat_id)
            
            print('- Waiting for NAT Gateways to be deleted...')
            waiter = ec2_client.get_waiter('nat_gateway_deleted')
            for nat_id in nat_gateway_ids:
                waiter.wait(NatGatewayIds=[nat_id])
            
            print('- NAT Gateways deleted successfully')
            
            if allocation_ids:
                print(f'- Releasing {len(allocation_ids)} Elastic IP(s): {allocation_ids}')
                for alloc_id in allocation_ids:
                    try:
                        ec2_client.release_address(AllocationId=alloc_id)
                        print(f'- Elastic IP {alloc_id} released successfully')
                    except Exception as e:
                        print(f'- Warning: Could not release Elastic IP {alloc_id}: {e}')
            else:
                print('- No Elastic IPs found to release')
        else:
            print('- No NAT Gateways found to delete')
            
    except Exception as e:
        print(f'- Error deleting NAT Gateways: {e}')


def delete_internet_gateways(ec2_client, vpc_id):
    try:
        print('- Finding Internet Gateways to delete')
        
        response = ec2_client.describe_internet_gateways(
            Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
        )
        
        for igw in response['InternetGateways']:
            igw_id = igw['InternetGatewayId']
            print(f'- Detaching and deleting Internet Gateway: {igw_id}')
            
            ec2_client.detach_internet_gateway(
                InternetGatewayId=igw_id,
                VpcId=vpc_id
            )
            
            ec2_client.delete_internet_gateway(InternetGatewayId=igw_id)
            print(f'- Internet Gateway {igw_id} deleted successfully')
            
        if not response['InternetGateways']:
            print('- No Internet Gateways found to delete')
            
    except Exception as e:
        print(f'- Error deleting Internet Gateways: {e}')


def delete_subnets(ec2_client, vpc_id):
    try:
        print('- Finding subnets to delete')
        
        response = ec2_client.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        subnet_ids = [subnet['SubnetId'] for subnet in response['Subnets']]
        
        if subnet_ids:
            print(f'- Deleting {len(subnet_ids)} subnet(s): {subnet_ids}')
            for subnet_id in subnet_ids:
                ec2_client.delete_subnet(SubnetId=subnet_id)
                print(f'- Subnet {subnet_id} deleted')
            
            print('- All subnets deleted successfully')
        else:
            print('- No subnets found to delete')
            
    except Exception as e:
        print(f'- Error deleting subnets: {e}')


def delete_route_tables(ec2_client, vpc_id):
    try:
        print('- Finding route tables to delete')
        
        response = ec2_client.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        for route_table in response['RouteTables']:
            route_table_id = route_table['RouteTableId']
            
            is_main = any(
                assoc.get('Main', False) 
                for assoc in route_table.get('Associations', [])
            )
            
            if not is_main:
                print(f'- Deleting route table: {route_table_id}')
                ec2_client.delete_route_table(RouteTableId=route_table_id)
                print(f'- Route table {route_table_id} deleted')
        
        print('- All custom route tables deleted successfully')
            
    except Exception as e:
        print(f'- Error deleting route tables: {e}')


def delete_security_groups(ec2_client, vpc_id):
    try:
        print('- Finding security groups to delete')
        
        response = ec2_client.describe_security_groups(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        for sg in response['SecurityGroups']:
            if sg['GroupName'] != 'default':
                sg_id = sg['GroupId']
                print(f'- Deleting security group: {sg_id} ({sg["GroupName"]})')
                try:
                    ec2_client.delete_security_group(GroupId=sg_id)
                    print(f'- Security group {sg_id} deleted')
                except Exception as e:
                    print(f'- Warning: Could not delete security group {sg_id}: {e}')
        
        print('- All custom security groups deleted successfully')
            
    except Exception as e:
        print(f'- Error deleting security groups: {e}')


def delete_key_pair(ec2_client, key_name):
    try:
        print(f'- Deleting key pair: {key_name}')
        
        ec2_client.delete_key_pair(KeyName=key_name)
        print(f'- Key pair {key_name} deleted from AWS')
        
        pem_path = f'{key_name}.pem'
        if os.path.exists(pem_path):
            os.remove(pem_path)
            print(f'- Local key file {pem_path} deleted')
        else:
            print(f'- Local key file {pem_path} not found (already deleted?)')
            
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidKeyPair.NotFound' in str(e):
            print(f'- Key pair {key_name} not found in AWS (already deleted?)')
        else:
            print(f'- Error deleting key pair: {e}')
    except Exception as e:
        print(f'- Error deleting key pair: {e}')


def delete_vpc(ec2_client, vpc_id):
    try:
        print(f'- Deleting VPC: {vpc_id}')
        ec2_client.delete_vpc(VpcId=vpc_id)
        print(f'- VPC {vpc_id} deleted successfully')
            
    except Exception as e:
        print(f'- Error deleting VPC: {e}')


def cleanup_all_resources(ec2_client, vpc_id=None, vpc_name=None, key_name=None):
    try:
        if vpc_name and not vpc_id:
            print(f'- Searching for VPC with name: {vpc_name}')
            response = ec2_client.describe_vpcs(
                Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}]
            )
            
            if response['Vpcs']:
                vpc_id = response['Vpcs'][0]['VpcId']
                print(f'- Found VPC: {vpc_id}')
            else:
                print(f'- No VPC found with name: {vpc_name}')
                return
        
        if not vpc_id:
            print('- Error: No VPC ID or name provided')
            return
        
        print(f'- Starting cleanup for VPC: {vpc_id}')
        delete_ec2_instances(ec2_client, vpc_id)        
        delete_nat_gateways(ec2_client, vpc_id)
        delete_internet_gateways(ec2_client, vpc_id)
        delete_subnets(ec2_client, vpc_id)
        delete_route_tables(ec2_client, vpc_id)
        delete_security_groups(ec2_client, vpc_id)
        delete_vpc(ec2_client, vpc_id)

        if key_name:
            delete_key_pair(ec2_client, key_name)
        
        print(f'- Cleanup completed successfully for VPC: {vpc_id}')
        
    except Exception as e:
        print(f'Fatal error during cleanup: {e}')
        sys.exit(1)

