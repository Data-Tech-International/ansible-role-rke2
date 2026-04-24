from argparse import ArgumentParser
from subprocess import Popen, PIPE
from time import sleep
from psutil import net_connections
from random import randrange
from requests.auth import HTTPBasicAuth
from kubernetes import client, config  # noqa: E402
import requests
import base64

arguments = ArgumentParser()
arguments.add_argument('--kubectl_path', dest='kubectl_path', type=str, help='kubectl binary path', required=True)
arguments.add_argument('--kubeconfig', dest='kubeconfig', type=str, help='Path to the kubeconfig file to use', required=True)
arguments.add_argument('--namespace', dest='namespace', type=str, help='RabbitMQ namespace', default='infra')
arguments.add_argument('--rabbitmq_secret_name', dest='rabbitmq_secret_name', type=str, help='RabbitMQ default user secret name', default='rabbitmq-cluster-default-user')
arguments.add_argument('--rabbitmq_service_name', dest='rabbitmq_service_name', type=str, help='RabbitMQ Service name', default='services/rabbitmq-cluster')
arguments = arguments.parse_args()

def check_rabbitmq_queue_repl(rabbitmq_url :str, username :str, password :str, rabbimq_repl_nodes :int = 3) -> list | None:
  '''
  Check all quorum queues, and return those that are not fully replicated (replicated on less nodes than expected)

  :param rabbitmq_url: RabbitMQ management API URL
  :param rabbimq_repl_nodes: Number of RabbitMQ nodes that should have the queue replicated
  :param username: RabbitMQ management API username
  :param password: RabbitMQ management API password

  :return list: List of queues that are not fully replicated
  '''

  failed_queues = []
  url = f'{rabbitmq_url}/api/queues'
  response = requests.get(url, auth=HTTPBasicAuth(username,password))

  for queue in response.json():
    if queue['type'] == "quorum":
      if len(queue['online']) != rabbimq_repl_nodes:
        failed_queues.append(queue)

  if failed_queues:
    return failed_queues
  else:
    return None

# Get credentials
config.load_kube_config(f"{arguments.kubeconfig}")
v1_client = client.CoreV1Api()

try:
    # Get the secret
    secret = v1_client.read_namespaced_secret(name=f"{arguments.rabbitmq_secret_name}", namespace=f"{arguments.namespace}")

    username = base64.b64decode(secret.data['username']).decode('utf-8')
    password = base64.b64decode(secret.data['password']).decode('utf-8')

except client.exceptions.ApiException as exception:
    print(f"Error fetching secret: {exception}")

# Open port-forward
used_listening_ports = []

for conn in net_connections(kind='inet'):
  if conn.status == 'LISTEN':
    used_listening_ports.append(conn.laddr.port) # type: ignore

random_pf_port = randrange(32770,65500)

while random_pf_port in used_listening_ports:
  random_pf_port = randrange(32770,65500)

command = [f"{arguments.kubectl_path}", "port-forward", f"{arguments.rabbitmq_service_name}", f"{random_pf_port}:management", "--namespace", f"{arguments.namespace}", "--kubeconfig", f"{arguments.kubeconfig}"]
process = Popen(command, stdout=PIPE, stderr=PIPE)

sleep(5)

try:
  failed_queues = check_rabbitmq_queue_repl(rabbitmq_url=f"http://localhost:{random_pf_port}", username=username, password=password)

finally:
  process.terminate()
  process.wait()

if not failed_queues:
  exit(0)
else:
  print("CRITICAL: Quorum queues not in sync")
  for queue in failed_queues:
    print(f"FAIL - Queue [{queue['name']}] has {len(queue['online'])} nodes online")
  exit(1)
