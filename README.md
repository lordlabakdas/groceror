# grocerer - A platform for any shop owner

- An interface between the local grocery store owner and the consumer

- Primarily a store owner driven platform as opposed to ind. decider

- Allow the small business store to act like a supermarket
  - eg. rewards programs

- Social good
  - building micro-communities

-----

## Prerequisites

- Python 3.6 or higher
- pip (Python package manager)
- venv (Python virtual environment)

-----

## Installation

1. Clone the repository: `git clone git@github.com:lordlabakdas/groceror.git`

2. cd to app: `cd groceror`

## Install Dependencies

3. Create a virtual environment and activate it:
```shell
On Windows:
$ python -m venv venv
$ .\venv\Scripts\activate

On Mac/Linux:
$ python3 -m venv venv
$ source venv/bin/activate
```

4. Install the required packages using `requirements.txt`:
```bash
$ pip install -r requirements.txt
```

-----

## Running the application
5. Run the application
```bash
$ uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

6. Access the application at `http://localhost:8000` or `http://<public-ip>:8000`

-----

## Related services

### groceror-users

[groceror-users](https://github.com/lordlabakdas/groceror-users) is a companion microservice that consumes user lifecycle events published by groceror, stores them as an immutable event log in MongoDB, and exposes a Grafana dashboard via Prometheus metrics.

groceror publishes an event to RabbitMQ on each of these endpoints:

| Endpoint | Event |
|---|---|
| `POST /user/register` | `user_registered` |
| `POST /user/verify-otp` | `otp_verified` |
| `POST /user/set-profile` | `profile_updated` |
| `PUT /user/change-password` | `password_changed` |

See the [groceror-users README](https://github.com/lordlabakdas/groceror-users) for setup and running instructions.

### groceror-orders

[groceror-orders](https://github.com/lordlabakdas/groceror-orders) is a companion microservice that consumes order events published by groceror, stores them in MongoDB, and exposes analytics endpoints and a Grafana dashboard via Prometheus metrics.

groceror publishes an event to RabbitMQ on this endpoint:

| Endpoint | Event |
|---|---|
| `POST /order/create-order` | `order_created` |

See the [groceror-orders README](https://github.com/lordlabakdas/groceror-orders) for setup and running instructions.