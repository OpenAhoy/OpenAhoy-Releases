"""Same-entry immutable target inputs retain their first actual FD pins."""
from .draft_group_input_files import InputFiles
from .contracts import WCEError


class PinnedTargetFiles(InputFiles):
    def __init__(self,policy,guard):
        self._first={};self._poisoned=False
        super().__init__(policy,guard)

    def _entry(self,role,key,*,expected_sha=None):
        if self._poisoned:raise WCEError('GROUP_TARGET_FILE_CHANGED')
        evidence,pin=super()._entry(role,key,expected_sha=expected_sha)
        selected=(role,key);old=self._first.get(selected)
        if old is not None and old!=(pin,evidence.sha256):
            self._poisoned=True
            raise WCEError('GROUP_TARGET_FILE_CHANGED')
        self._first[selected]=(pin,evidence.sha256)
        return evidence,pin

    def prepare_release(self):
        if self._poisoned:raise WCEError('GROUP_TARGET_FILE_CHANGED')
        for (role,key),(pin,checksum)in tuple(self._first.items()):
            self._entry(role,key,expected_sha=checksum)
        self.pure_release_fence()

    def pure_release_fence(self):
        if self._poisoned:raise WCEError('GROUP_TARGET_FILE_CHANGED')
        try:
            self._pure_entries([(role,key,pin)for (role,key),(pin,_)in self._first.items()])
        except BaseException:
            self._poisoned=True
            raise

    def collective_fence(self):
        self.prepare_release()
