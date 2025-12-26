#!/bin/bash
set -e

exec > >(tee -a /var/log/user-data.log)
exec 2>&1

echo "Starting Manager setup at $(date)"

echo "Updating system packages"
apt-get update -y

echo "Installing MySQL Server"
DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server wget

echo "Starting MySQL service"
systemctl start mysql
systemctl enable mysql

echo "Configuring MySQL users"
mysql -u root <<'MYSQL_SETUP'
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'Root123!';
CREATE USER 'app_user'@'%' IDENTIFIED BY 'Mehdi1603!';
GRANT ALL PRIVILEGES ON *.* TO 'app_user'@'%';
CREATE USER 'replication_user'@'%' IDENTIFIED BY 'Repl123!';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'replication_user'@'%';
FLUSH PRIVILEGES;
MYSQL_SETUP

echo "Configuring MySQL for replication"
cat >> /etc/mysql/mysql.conf.d/mysqld.cnf <<'MYSQL_CONFIG'
[mysqld]
server-id=1
log-bin=mysql-bin
binlog-format=ROW
bind-address=0.0.0.0
MYSQL_CONFIG

echo "Restarting MySQL service"
systemctl restart mysql

sleep 10

echo "Installing Sakila database..."
cd /tmp
wget -q https://downloads.mysql.com/docs/sakila-db.tar.gz
tar -xzf sakila-db.tar.gz
cd sakila-db

mysql -u root -pRoot123! <<'SAKILA_INSTALL'
SOURCE sakila-schema.sql;
SOURCE sakila-data.sql;
SAKILA_INSTALL

echo "Sakila database installed successfully"

echo "Installing sysbench"
apt-get install -y sysbench

echo "Preparing sysbench benchmark on Manager..."
sysbench /usr/share/sysbench/oltp_read_only.lua \
    --mysql-db=sakila \
    --mysql-user=app_user \
    --mysql-password=Mehdi1603! \
    prepare

echo "Running sysbench benchmark on Manager..."
sysbench /usr/share/sysbench/oltp_read_only.lua \
    --mysql-db=sakila \
    --mysql-user=app_user \
    --mysql-password=Mehdi1603! \
    run > /tmp/sysbench_results.txt 2>&1

echo "Sysbench benchmark completed"

mysql -u root -pRoot123! -e "SHOW MASTER STATUS\G"

touch /tmp/manager_setup_complete
echo "Manager setup completed at $(date)"