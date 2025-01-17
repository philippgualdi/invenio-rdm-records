# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 CERN
#
# Invenio-RDM-Records is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see LICENSE file for
# more details.

"""PID service tasks tests."""

from unittest import mock

import pytest
from invenio_pidstore.models import PIDStatus

from invenio_rdm_records.proxies import current_rdm_records
from invenio_rdm_records.services.pids.tasks import register_or_update_pid


@pytest.fixture(scope="module")
def mock_datacite_client(mock_datacite_client):
    """Mock DataCite client API calls."""
    with mock.patch.object(mock_datacite_client, "api"):
        yield mock_datacite_client


def test_register_pid(
    running_app,
    search_clear,
    minimal_record,
    superuser_identity,
    mock_datacite_client,
):
    """Registers a PID."""
    service = current_rdm_records.records_service
    draft = service.create(superuser_identity, minimal_record)
    draft = service.pids.create(superuser_identity, draft.id, "doi")
    doi = draft["pids"]["doi"]["identifier"]
    provider = service.pids.pid_manager._get_provider("doi", "datacite")
    pid = provider.get(pid_value=doi)
    record = service.record_cls.publish(draft._record)
    record.pids = {pid.pid_type: {"identifier": pid.pid_value, "provider": "datacite"}}
    record.metadata = draft["metadata"]
    record.register()
    record.commit()
    assert pid.status == PIDStatus.NEW
    pid.reserve()
    assert pid.status == PIDStatus.RESERVED
    register_or_update_pid(recid=record["id"], scheme="doi")
    assert pid.status == PIDStatus.REGISTERED
    mock_datacite_client.api.public_doi.assert_has_calls(
        [
            mock.call(
                metadata={
                    "identifiers": [{"identifier": doi, "identifierType": "DOI"}],
                    "types": {"resourceTypeGeneral": "Image", "resourceType": "Photo"},
                    "publisher": "Acme Inc",
                    "creators": [
                        {
                            "givenName": "Troy",
                            "nameIdentifiers": [],
                            "familyName": "Brown",
                            "nameType": "Personal",
                            "name": "Brown, Troy",
                        },
                        {
                            "nameIdentifiers": [],
                            "nameType": "Organizational",
                            "name": "Troy Inc.",
                        },
                    ],
                    "titles": [{"title": "A Romans story"}],
                    "schemaVersion": "http://datacite.org/schema/kernel-4",
                    "publicationYear": "2020",
                    "dates": [{"date": "2020-06-01", "dateType": "Issued"}],
                },
                url=f"https://127.0.0.1:5000/doi/{doi}",
                doi=doi,
            )
        ]
    )


def test_update_pid(
    running_app,
    search_clear,
    minimal_record,
    mocker,
    superuser_identity,
    mock_datacite_client,
):
    """No pid provided, creating one by default."""
    service = current_rdm_records.records_service
    draft = service.create(superuser_identity, minimal_record)
    record = service.publish(superuser_identity, draft.id)

    oai = record["pids"]["oai"]["identifier"]
    doi = record["pids"]["doi"]["identifier"]
    parent_doi = record["parent"]["pids"]["doi"]["identifier"]
    provider = service.pids.pid_manager._get_provider("doi", "datacite")
    pid = provider.get(pid_value=doi)
    assert pid.status == PIDStatus.REGISTERED
    parent_provider = service.pids.parent_pid_manager._get_provider("doi", "datacite")
    parent_pid = parent_provider.get(pid_value=parent_doi)
    assert parent_pid.status == PIDStatus.REGISTERED

    # we do not explicitly call the update_pid task
    # we check that the lower level provider update is called
    record_edited = service.edit(superuser_identity, record.id)
    assert mock_datacite_client.api.update_doi.called is False
    service.publish(superuser_identity, record_edited.id)

    mock_datacite_client.api.update_doi.assert_has_calls(
        [
            mock.call(
                metadata={
                    "schemaVersion": "http://datacite.org/schema/kernel-4",
                    "types": {"resourceTypeGeneral": "Image", "resourceType": "Photo"},
                    "creators": [
                        {
                            "name": "Brown, Troy",
                            "familyName": "Brown",
                            "nameIdentifiers": [],
                            "nameType": "Personal",
                            "givenName": "Troy",
                        },
                        {
                            "name": "Troy Inc.",
                            "nameIdentifiers": [],
                            "nameType": "Organizational",
                        },
                    ],
                    "relatedIdentifiers": [
                        {
                            "relatedIdentifier": parent_doi,
                            "relationType": "IsVersionOf",
                            "relatedIdentifierType": "DOI",
                        }
                    ],
                    "titles": [{"title": "A Romans story"}],
                    "dates": [{"date": "2020-06-01", "dateType": "Issued"}],
                    "identifiers": [
                        {"identifier": doi, "identifierType": "DOI"},
                        {
                            "identifier": oai,
                            "identifierType": "oai",
                        },
                    ],
                    "publicationYear": "2020",
                    "publisher": "Acme Inc",
                },
                doi=doi,
                url=f"https://127.0.0.1:5000/doi/{doi}",
            ),
            mock.call(
                metadata={
                    "schemaVersion": "http://datacite.org/schema/kernel-4",
                    "types": {"resourceTypeGeneral": "Image", "resourceType": "Photo"},
                    "creators": [
                        {
                            "name": "Brown, Troy",
                            "familyName": "Brown",
                            "nameIdentifiers": [],
                            "nameType": "Personal",
                            "givenName": "Troy",
                        },
                        {
                            "name": "Troy Inc.",
                            "nameIdentifiers": [],
                            "nameType": "Organizational",
                        },
                    ],
                    "relatedIdentifiers": [
                        {
                            "relatedIdentifier": doi,
                            "relationType": "HasVersion",
                            "relatedIdentifierType": "DOI",
                        }
                    ],
                    "titles": [{"title": "A Romans story"}],
                    "dates": [{"date": "2020-06-01", "dateType": "Issued"}],
                    "identifiers": [
                        {"identifier": parent_doi, "identifierType": "DOI"}
                    ],
                    "publicationYear": "2020",
                    "publisher": "Acme Inc",
                },
                doi=parent_doi,
                url=f"https://127.0.0.1:5000/doi/{parent_doi}",
            ),
        ],
        any_order=True,
    )
