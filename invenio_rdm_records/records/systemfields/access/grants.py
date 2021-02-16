# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2021 TU Wien.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Grants classes for the access system field."""

from base64 import b64decode, b64encode

from flask_principal import RoleNeed, UserNeed
from invenio_access.permissions import SystemRoleNeed
from invenio_accounts.models import Role, User


class Grant:
    """Grant for a specific permission level on a record."""

    def __init__(
        self, subject, permission_level, subject_type=None, subject_id=None
    ):
        """Permission grant for a specific subject (e.g. a user).

        :param subject: The subject of the permission grant.
        :param permission_level: The granted permission level.
        :param subject_type: An override for the subject's type.
        :param subject_id: An override for the subject's ID.
        """
        self.permission_level = permission_level
        self._subject = subject
        self._subject_type = subject_type
        self._subject_id = subject_id

    @property
    def subject(self):
        """The entity that is subject to the Grant.

        Note: If the subject entity has not been cached yet, this operation
        will trigger a database query.
        """
        if self._subject is None:
            if self._subject_type == "user":
                self._subject = User.query.get(self._subject_id)
            elif self._subject_type == "role":
                self._subject = Role.query.get(self._subject_id)

        return self._subject

    @property
    def subject_type(self):
        """The type of the Grant's subject (user, role or sysrole)."""
        if self._subject_type:
            return self._subject_type

        if isinstance(self.subject, User):
            return "user"

        elif isinstance(self.subject, Role):
            return "role"

        else:
            # if it's nothing else, it's gonna be a system role
            # (which doesn't have a persisted subject entity)
            return "sysrole"

    @property
    def subject_id(self):
        """The ID of the Grant's subject."""
        if self._subject_id:
            return self._subject_id

        return self.subject.id

    def covers(self, permission):
        """Check if this Grant covers the specified permission."""
        # TODO check this via a permission hierarchy
        return True

    def to_need(self):
        """Create the need that this grant provides."""
        if self.subject_type == "user":
            need = UserNeed(self.subject.id)

        elif self.subject_type == "role":
            # according to invenio_access.utils:get_identity, RoleNeeds
            # take the roles' names
            need = RoleNeed(self.subject.name)

        elif self.subject_type == "sysrole":
            # system roles don't have a model class behind them, so
            # it's probably best to go with the subject_id
            need = SystemRoleNeed(self.subject_id)

        return need

    def to_token(self):
        """Dump the Grant to a grant token."""
        # TODO
        # do something similar to JWT: base64-encode and separate with dots
        # this ensures that we can always separate the values again
        # (b/c the base64 alphabet doesn't contain the dot)
        return "{}.{}.{}".format(
            b64encode(str(self.subject_type).encode()).decode(),
            b64encode(str(self.subject_id).encode()).decode(),
            b64encode(str(self.permission_level).encode()).decode(),
        )

    def to_dict(self):
        """Dump the Grant to a dictionary."""
        return {
            "subject": self.subject_type,
            "id": self.subject_id,
            "level": self.permission_level,
        }

    @classmethod
    def from_string_parts(
        cls, subject_type, subject_id, permission_level, fetch_subject=False
    ):
        """Create a Grant from the specified parts.

        :param subject_type: The grant subject's type (user, role or sysrole).
        :param subject_id: The grant subject's ID.
        :param permission_level: The grant's permission level.
        :param fetch_subject: Whether to fetch the subject entity from the
                              database eagerly.
        """
        if subject_type not in ["user", "role", "sysrole"]:
            raise ValueError("unknown subject type: {}".format(subject_type))

        if fetch_subject:
            if subject_type == "user":
                subject = User.query.get(subject_id)
            elif subject_type == "role":
                subject = Role.query.get(subject_id)
        else:
            subject = None

        return cls(
            subject=subject,
            permission_level=permission_level,
            subject_type=subject_type,
            subject_id=subject_id,
        )

    @classmethod
    def from_token(cls, token):
        """Parse the grant token into a Grant."""
        # TODO
        subject_type, subject_id, permission_level = (
            b64decode(val).decode() for val in token.split(".")
        )

        return cls.from_string_parts(
            subject_type, subject_id, permission_level
        )

    @classmethod
    def from_dict(cls, dict_):
        """Parse the dictionary into a Grant."""
        subject_type = dict_["subject"]
        subject_id = dict_["id"]
        permission_level = dict_["level"]

        return cls.from_string_parts(
            subject_type, subject_id, permission_level
        )

    def __hash__(self):
        """Return hash(self)."""
        return (
            hash(self.subject_type)
            + hash(self.subject_id)
            + hash(self.permission_level)
        )

    def __eq__(self, other):
        """Return self == other."""
        if type(self) != type(other):
            return False

        return (
            self.subject_type == other.subject_type
            and self.subject_id == other.subject_id
            and self.permission_level == other.permission_level
        )

    def __ne__(self, other):
        """Return self != other."""
        return not self == other

    def __repr__(self):
        """Return repr(self)."""
        return "<{} (subject: {}, id: {}, level: {})>".format(
            type(self).__name__,
            self.subject_type,
            self.subject_id,
            self.permission_level,
        )


class Grants(set):
    """Set of grants for various permission levels on a record."""

    grant_cls = Grant

    def __init__(self, grants=None):
        """Create a new set of Grants."""
        super().__init__(grants or [])

    def needs(self, permission):
        """Get allowed needs for the given permission level."""
        needs = {grant.to_need() for grant in self if grant.covers(permission)}
        return needs

    def dump(self):
        """Dump the grants as a list of grant dictionaries."""
        return [grant.to_dict() for grant in self]