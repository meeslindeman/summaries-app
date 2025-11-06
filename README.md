# summaries-app


## Deployment
This project is available at https://summaries.lindeman.it. It runs on a MicroK8s cluster. The cluster must have some settings before deployment, ask your cluster admin to do this for you:

```bash
kubectl create secret generic summaries-app \                       
  --from-literal=REFRESH_TOKEN='<your-refresh-token>' \
  --from-literal=OPENAI_API_KEY='<your-openai-api-key>' \
  -n meeslindeman
```

To deploy a new version make sure you have an account on the Lindeman IT Container registry. You must login before pushing images:
```bash
docker login containers.lindeman.it -u user -p password
```

You can now build your image and push it to the registry:
```bash
docker build -t containers.lindeman.it/summaries.lindeman.it:1.0.0 .
docker push containers.lindeman.it/summaries.lindeman.it:1.0.0
```

Make sure to update the version (`1.0.0` in the above example) every time you want to do an update.

After you have pushed a new image to the registry, you need to update the Kubernetes Deployment Manifest (`deployment/manifest.yaml`) to reflect the version update of the image. The K8s cluster will pick up your changes automatically and will deploy your latest version for you.


