from argparse import ArgumentParser
from kubernetes import client, config  # noqa: E402

arguments = ArgumentParser()
arguments.add_argument(
    "--kubeconfig",
    dest="kubeconfig",
    type=str,
    help="Path to the kubeconfig file to use",
    required=True,
)
arguments = arguments.parse_args()


def get_containers_not_ready(kubeconfig: str) -> list | None:
    config.load_kube_config(kubeconfig)
    v1_client = client.CoreV1Api()
    pods = v1_client.list_pod_for_all_namespaces()
    non_ready_cont = []

    for pod in pods.items:
        for container in pod.status.container_statuses:
            if not container.ready:
                if (container.state.terminated and container.state.terminated.exit_code == 0):
                    continue
                else:
                    container_list_object = {
                        'name': f"{container.name}",
                        'pod_name': f"{pod.metadata.name}"
                    }
                    non_ready_cont.append(container_list_object)

    if non_ready_cont:
        return non_ready_cont
    else:
        return None


not_ready_containers = get_containers_not_ready(kubeconfig=arguments.kubeconfig)

if not_ready_containers:
    print("Some containers not reporting ready status:")
    for cont in not_ready_containers:
        print(f'Container [{cont["name"]}] in pod [{cont["pod_name"]}] not ready or terminated with 0')
    exit(1)
else:
    exit(0)
