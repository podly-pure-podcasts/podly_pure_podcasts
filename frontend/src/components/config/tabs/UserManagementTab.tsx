import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { authApi } from '../../../services/api';
import { useAuth } from '../../../contexts/AuthContext';
import { useConfigContext } from '../ConfigContext';
import { Section, Field, SaveButton } from '../shared';
import { backendDateMs, formatBackendDateTime } from '../../../utils/datetime';
import type { ManagedUser } from '../../../types';

export default function UserManagementTab() {
  const { changePassword, refreshUser, user, logout } = useAuth();
  const { pending, setField, handleSave, isSaving } = useConfigContext();

  const {
    data: managedUsers,
    isLoading: usersLoading,
    refetch: refetchUsers,
  } = useQuery<ManagedUser[]>({
    queryKey: ['auth-users'],
    queryFn: async () => {
      const response = await authApi.listUsers();
      return response.users;
    },
  });

  const totalUsers = useMemo(() => managedUsers?.length ?? 0, [managedUsers]);
  const limitValue = pending?.app?.user_limit_total ?? null;

  return (
    <div className="space-y-6">
      <AccountSecuritySection
        changePassword={changePassword}
        refreshUser={refreshUser}
      />
      <UserManagementSection
        currentUser={user}
        refreshUser={refreshUser}
        logout={logout}
        managedUsers={managedUsers}
        usersLoading={usersLoading}
        refetchUsers={refetchUsers}
      />
      {pending && (
        <UserLimitSection
          currentUsers={totalUsers}
          userLimit={limitValue}
          onChangeLimit={(value) =>
            setField(
              ['app', 'user_limit_total'],
              value === '' ? null : Number(value)
            )
          }
          onSave={handleSave}
          isSaving={isSaving}
          isLoadingUsers={usersLoading}
        />
      )}
    </div>
  );
}

// --- Account Security Section ---
interface AccountSecurityProps {
  changePassword: (current: string, next: string) => Promise<void>;
  refreshUser: () => Promise<void>;
}

function AccountSecuritySection({ changePassword, refreshUser }: AccountSecurityProps) {
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);

  const handlePasswordSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (passwordForm.next !== passwordForm.confirm) {
      toast.error('New passwords do not match.');
      return;
    }

    setPasswordSubmitting(true);
    try {
      await changePassword(passwordForm.current, passwordForm.next);
      toast.success('Password updated. Update PODLY_ADMIN_PASSWORD to match.');
      setPasswordForm({ current: '', next: '', confirm: '' });
      await refreshUser();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update password.'));
    } finally {
      setPasswordSubmitting(false);
    }
  };

  return (
    <Section title="Your account">
      <form className="grid max-w-md gap-4" onSubmit={handlePasswordSubmit}>
        <Field label="Current password">
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={passwordForm.current}
            onChange={(event) =>
              setPasswordForm((prev) => ({ ...prev, current: event.target.value }))
            }
            required
          />
        </Field>
        <Field label="New password">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={passwordForm.next}
            onChange={(event) =>
              setPasswordForm((prev) => ({ ...prev, next: event.target.value }))
            }
            required
          />
        </Field>
        <Field label="Confirm new password">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={passwordForm.confirm}
            onChange={(event) =>
              setPasswordForm((prev) => ({ ...prev, confirm: event.target.value }))
            }
            required
          />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={passwordSubmitting}
          >
            {passwordSubmitting ? 'Changing…' : 'Change password'}
          </button>
          <p className="text-xs text-gray-600">
            Afterwards, set <code className="font-mono">PODLY_ADMIN_PASSWORD</code> to the new password.
          </p>
        </div>
      </form>
    </Section>
  );
}

// --- User Limit Section ---
interface UserLimitSectionProps {
  currentUsers: number;
  userLimit: number | null;
  onChangeLimit: (value: string) => void;
  onSave: () => void;
  isSaving: boolean;
  isLoadingUsers: boolean;
}

function UserLimitSection({ currentUsers, userLimit, onChangeLimit, onSave, isSaving, isLoadingUsers }: UserLimitSectionProps) {
  const limitReached = userLimit !== null && userLimit > 0 && currentUsers >= userLimit;
  return (
    <Section title="User limit" collapsible>
      <Field
        label="Total users allowed"
        hint="Leave blank for unlimited; 0 blocks new users. Applies only when authentication is enabled."
      >
        <input
          className="input sm:max-w-xs"
          type="number"
          min={0}
          value={userLimit ?? ''}
          onChange={(event) => onChangeLimit(event.target.value)}
          placeholder="Unlimited"
        />
      </Field>
      <p className={`text-sm tabular-nums ${limitReached ? 'text-red-600' : 'text-gray-600'}`}>
        {isLoadingUsers ? 'Loading users…' : `${currentUsers} current ${currentUsers === 1 ? 'user' : 'users'}.`}
        {limitReached && ` Limit reached: new users are blocked until the total drops below ${userLimit}.`}
      </p>
      <SaveButton onSave={onSave} isPending={isSaving} />
    </Section>
  );
}

// --- User Management Section ---
interface UserManagementProps {
  currentUser: { id: number; username: string; role: string } | null;
  refreshUser: () => Promise<void>;
  logout: () => void;
  managedUsers: ManagedUser[] | undefined;
  usersLoading: boolean;
  refetchUsers: () => Promise<unknown>;
}

function UserManagementSection({ currentUser, refreshUser, logout, managedUsers, usersLoading, refetchUsers }: UserManagementProps) {
  const [newUser, setNewUser] = useState({ username: '', password: '', confirm: '', role: 'user' });
  const [activeResetUser, setActiveResetUser] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetConfirm, setResetConfirm] = useState('');

  const sortedUsers = useMemo(() => {
    if (!managedUsers) {
      return [];
    }
    return [...managedUsers].sort(
      (a, b) => backendDateMs(b.created_at) - backendDateMs(a.created_at)
    );
  }, [managedUsers]);
  const adminCount = useMemo(
    () => sortedUsers.filter((u) => u.role === 'admin').length,
    [sortedUsers]
  );

  const handleCreateUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const username = newUser.username.trim();
    if (!username) {
      toast.error('Username is required.');
      return;
    }
    if (newUser.password !== newUser.confirm) {
      toast.error('Passwords do not match.');
      return;
    }

    try {
      await authApi.createUser({
        username,
        password: newUser.password,
        role: newUser.role,
      });
      toast.success(`User '${username}' created.`);
      setNewUser({ username: '', password: '', confirm: '', role: 'user' });
      await refetchUsers();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to create user.'));
    }
  };

  const handleRoleChange = async (username: string, role: string) => {
    try {
      await authApi.updateUser(username, { role });
      toast.success(`Updated role for ${username}.`);
      await refetchUsers();
      if (currentUser && currentUser.username === username) {
        await refreshUser();
      }
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update role.'));
    }
  };

  const handleAllowanceChange = async (username: string, allowance: string) => {
    const val = allowance === '' ? null : parseInt(allowance, 10);
    if (val !== null && isNaN(val)) return;

    try {
      await authApi.updateUser(username, { manual_feed_allowance: val });
      toast.success(`Updated allowance for ${username}.`);
      await refetchUsers();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update allowance.'));
    }
  };

  const handleResetPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activeResetUser) {
      return;
    }
    if (resetPassword !== resetConfirm) {
      toast.error('Passwords do not match.');
      return;
    }

    try {
      await authApi.updateUser(activeResetUser, { password: resetPassword });
      toast.success(`Password updated for ${activeResetUser}.`);
      setActiveResetUser(null);
      setResetPassword('');
      setResetConfirm('');
      await refetchUsers();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update password.'));
    }
  };

  const handleDeleteUser = async (username: string) => {
    const isSelf = currentUser?.username === username;
    const confirmed = window.confirm(
      `Delete user '${username}'? Their account and access are removed permanently and this cannot be undone.${
        isSelf ? ' You will be signed out.' : ''
      }`
    );
    if (!confirmed) {
      return;
    }
    try {
      await authApi.deleteUser(username);
      toast.success(`Deleted user '${username}'.`);
      await refetchUsers();
      if (currentUser && currentUser.username === username) {
        logout();
      }
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to delete user.'));
    }
  };

  const resetForm = (managed: ManagedUser) => (
    <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={handleResetPassword}>
      <Field label={`New password for ${managed.username}`}>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          value={resetPassword}
          onChange={(event) => setResetPassword(event.target.value)}
          required
        />
      </Field>
      <Field label="Confirm new password">
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          value={resetConfirm}
          onChange={(event) => setResetConfirm(event.target.value)}
          required
        />
      </Field>
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <button type="submit" className="btn btn-secondary">
          Change password
        </button>
        <p className="text-xs text-gray-600">Share the new password securely.</p>
      </div>
    </form>
  );

  return (
    <Section title="Users">
      {usersLoading && <p className="text-sm text-gray-600">Loading users…</p>}
      {!usersLoading && (!managedUsers || managedUsers.length === 0) && (
        <p className="text-sm text-gray-600">No additional users configured.</p>
      )}
      {!usersLoading && managedUsers && managedUsers.length > 0 && (
        <ul className="divide-y divide-gray-200">
          {sortedUsers.map((managed) => {
            const disableDemotion = managed.role === 'admin' && adminCount <= 1;
            const isActive = activeResetUser === managed.username;
            const allowance = managed.feed_allowance ?? 0;
            const subscriptionStatus = managed.feed_subscription_status ?? 'inactive';

            return (
              <li key={managed.id} className="py-4 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <div className="break-words text-sm font-semibold text-gray-900">{managed.username}</div>
                  <div className="mt-0.5 text-xs text-gray-600">
                    Added {formatBackendDateTime(managed.created_at)} • {allowance} feeds • Subscription {subscriptionStatus}
                    {managed.last_active && (
                      <> • Last active {formatBackendDateTime(managed.last_active)}</>
                    )}
                  </div>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Role">
                    <select
                      className="input"
                      value={managed.role}
                      onChange={(event) => {
                        const nextRole = event.target.value;
                        if (nextRole !== managed.role) {
                          void handleRoleChange(managed.username, nextRole);
                        }
                      }}
                      disabled={disableDemotion}
                    >
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                    </select>
                  </Field>
                  <Field label="Feed allowance override" hint="Blank uses the subscription's allowance.">
                    <input
                      className="input tabular-nums"
                      type="number"
                      min="0"
                      placeholder="None"
                      defaultValue={managed.manual_feed_allowance ?? ''}
                      onBlur={(e) => {
                        const val = e.target.value;
                        const current = managed.manual_feed_allowance?.toString() ?? '';
                        if (val !== current) {
                          void handleAllowanceChange(managed.username, val);
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.currentTarget.blur();
                        }
                      }}
                    />
                  </Field>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setActiveResetUser(isActive ? null : managed.username);
                      setResetPassword('');
                      setResetConfirm('');
                    }}
                  >
                    {isActive ? 'Cancel' : 'Change password'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => void handleDeleteUser(managed.username)}
                    disabled={disableDemotion}
                    title={disableDemotion ? 'The last admin cannot be deleted.' : undefined}
                  >
                    Delete user
                  </button>
                </div>
                {isActive && resetForm(managed)}
              </li>
            );
          })}
        </ul>
      )}

      <form
        className="grid gap-4 border-t border-gray-200 pt-5 sm:grid-cols-2"
        onSubmit={handleCreateUser}
      >
        <h4 className="text-sm font-semibold text-gray-900 sm:col-span-2">Add user</h4>
        <div className="sm:col-span-2">
          <Field label="Username">
            <input
              className="input"
              type="text"
              autoComplete="off"
              value={newUser.username}
              onChange={(event) => setNewUser((prev) => ({ ...prev, username: event.target.value }))}
              placeholder="new_user"
              required
            />
          </Field>
        </div>
        <Field label="Password">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={newUser.password}
            onChange={(event) => setNewUser((prev) => ({ ...prev, password: event.target.value }))}
            required
          />
        </Field>
        <Field label="Confirm password">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={newUser.confirm}
            onChange={(event) => setNewUser((prev) => ({ ...prev, confirm: event.target.value }))}
            required
          />
        </Field>
        <Field label="Role">
          <select
            className="input"
            value={newUser.role}
            onChange={(event) => setNewUser((prev) => ({ ...prev, role: event.target.value }))}
          >
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </Field>
        <div className="sm:col-span-2">
          <button type="submit" className="btn btn-secondary">
            Add user
          </button>
        </div>
      </form>
    </Section>
  );
}

// Helper function
function getErrorMessage(error: unknown, fallback = 'Request failed.') {
  if (error && typeof error === 'object') {
    const err = error as {
      response?: { data?: { error?: string; message?: string } };
      message?: string;
    };
    return err.response?.data?.error || err.response?.data?.message || err.message || fallback;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
