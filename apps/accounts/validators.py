import datetime
from django.core.exceptions import ValidationError
from django.db.models import Q
from django_password_validators.password_history.models import (
    PasswordHistory,
    UserPasswordHistoryConfig,
)
from django_password_validators.password_history.password_validation import UniquePasswordsValidator


class UniqueAndMinAgedPasswordsValidator(UniquePasswordsValidator):

    def __init__(self,
                 password_min_age=60 * 60 * 24,
                 password_reuse_interval=60 * 60 * 24 * 120,
                 password_expire=60 * 60 * 24 * 30):

        msg1 = "Invalid OPTIONS, password_min_age < password_reuse_interval expected, " \
               "but having password_min_age({}) < password_reuse_interval({})"
        msg2 = "Invalid OPTIONS, password_expire < password_reuse_interval expected, " \
               "but having password_expire({}) < password_reuse_interval({})"
        msg3 = "Invalid OPTIONS, password_min_age < password_expire expected, " \
               "but having password_expire({}) < password_reuse_interval({})"

        if password_min_age > 0 and password_reuse_interval > 0:
            assert password_min_age <= password_reuse_interval, \
                msg1.format(password_min_age, password_reuse_interval)
        if password_expire > 0 and password_reuse_interval > 0:
            assert password_expire <= password_reuse_interval, \
                msg2.format(password_expire, password_reuse_interval)
        if password_min_age > 0 and password_expire > 0:
            assert password_min_age <= password_expire, \
                msg3.format(password_min_age, password_expire)
        self.password_min_age = password_min_age
        self.password_reuse_interval = password_reuse_interval
        self.password_expire = password_expire

    def validate(self, password, user=None):
        # override original validation check
        # since it is more restrict than what we want
        # super().validate(password, user)

        if not self._user_ok(user):
            return

        #
        #                                                 |<--min password age-->|
        #                     |<------------no reuse window--------------------->|
        #  ------p0-----p1----+---p2-----p3----------p4---------p5---------------+
        #                                                                        ^
        #                                                                   cur_time_utc
        #  given new password p:
        #  (1) p's hash colides with any px in 'no reuse window' => validation fails
        #  (2) p's hash does not colide with any px in 'no reuse window'
        #      or the window is empty => further check 'min password age'
        #  (3) there are px in 'no reuse window' => if there is no px in 'min password age'
        #      like p5 => validation pass
        #  (4) no px in 'no reuse window' (hence no px in 'min password age'
        #      since it's asserted that password_min_age < password_reuse_interval) => pass validation
        #
        cur_time_utc = datetime.datetime.now(datetime.timezone.utc)
        for user_config in UserPasswordHistoryConfig.objects.filter(user=user):
            password_hash = user_config.make_password_hash(password)
            passwds = None
            try:
                if self.password_reuse_interval > 0:
                    # only check invalid reuse (colide) within reuse_interval
                    reuse_datetime = cur_time_utc - datetime.timedelta(0, self.password_reuse_interval)
                    passwds = PasswordHistory.objects.filter(
                        Q(date__gt=reuse_datetime), user_config=user_config
                    ).order_by('-date')
                else:
                    # no reuse_interval, check all past passwords for colide
                    passwds = PasswordHistory.objects.filter(
                        user_config=user_config
                    ).order_by('-date')

                for p in passwds:
                    if p.password == password_hash:
                        # check invalid re-use (colide) within password reuse interval
                        raise ValidationError(
                            ("You can not use a password that is already"
                             " used in this application within password re-use interval: {}.")
                            .format(str(datetime.timedelta(seconds=self.password_reuse_interval))),
                            code='password_used'
                        )
            except PasswordHistory.DoesNotExist:
                pass

            if self.password_min_age > 0 and passwds is not None and passwds.first() is not None:
                if (datetime.datetime.now(datetime.timezone.utc) - passwds.first().date).total_seconds() <= self.password_min_age:
                    # change password too soon
                    raise ValidationError(
                        "You can not change password that does not satisfy minimum password age: {}."
                        .format(str(datetime.timedelta(seconds=self.password_min_age))),
                        code='password_used'
                    )

    def get_help_text(self):
        help_msg = ('Change password not allowed within mimimum password age: {}, and'
                    ' your new password can not be identical to any of the '
                    'previously entered in the past {}').format(
            str(datetime.timedelta(seconds=self.password_min_age)),
            str(datetime.timedelta(seconds=self.password_reuse_interval)))
        return help_msg

    def password_expired(self, user=None):
        passwd_expired = False
        if user.is_staff or user.is_superuser:
            # for staff and above do not enforce password expire
            return passwd_expired
        if self.password_expire <= 0:
            # password never expire, password_expire set to 0 or negative
            # effectively disable password expire
            return passwd_expired
        for user_config in UserPasswordHistoryConfig.objects.filter(user=user):
            passwds = None
            try:
                # only check invalid reuse within reuse_interval
                passwds = PasswordHistory.objects.filter(
                    user_config=user_config
                ).order_by('-date')
            except PasswordHistory.DoesNotExist:
                pass
            if passwds is not None and passwds.first() is not None:
                if (datetime.datetime.now(datetime.timezone.utc) - passwds.first().date).total_seconds() >= self.password_expire:
                    # the elapsed time since last password change / create is more than password_expire
                    passwd_expired = True
        return passwd_expired
