import React, { useState, useEffect } from 'react';
import { getUsers, createUser, updateUser, deleteUser } from '@/services/api';
import { validateEmail } from '@/utils/validators';

// HUMAN ASSISTANCE NEEDED
// The following component requires additional refinement and error handling for production readiness.
// Please review and enhance the code, particularly focusing on:
// - Improved error handling and user feedback
// - Accessibility improvements
// - Performance optimizations
// - Security considerations for user management
// - Proper state management for larger applications
// - Internationalization support

const UserManagement: React.FC = () => {
  const [users, setUsers] = useState<any[]>([]);
  const [newUser, setNewUser] = useState({ name: '', email: '', role: '' });
  const [editingUser, setEditingUser] = useState<any | null>(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const fetchedUsers = await getUsers();
      setUsers(fetchedUsers);
    } catch (error) {
      setMessage('Error fetching users');
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateEmail(newUser.email)) {
      setMessage('Invalid email address');
      return;
    }
    try {
      await createUser(newUser);
      setNewUser({ name: '', email: '', role: '' });
      fetchUsers();
      setMessage('User created successfully');
    } catch (error) {
      setMessage('Error creating user');
    }
  };

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editingUser && !validateEmail(editingUser.email)) {
      setMessage('Invalid email address');
      return;
    }
    try {
      await updateUser(editingUser.id, editingUser);
      setEditingUser(null);
      fetchUsers();
      setMessage('User updated successfully');
    } catch (error) {
      setMessage('Error updating user');
    }
  };

  const handleDeleteUser = async (userId: string) => {
    try {
      await deleteUser(userId);
      fetchUsers();
      setMessage('User deleted successfully');
    } catch (error) {
      setMessage('Error deleting user');
    }
  };

  return (
    <div>
      <h1>User Management</h1>
      
      <h2>Create New User</h2>
      <form onSubmit={handleCreateUser}>
        <input
          type="text"
          placeholder="Name"
          value={newUser.name}
          onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
          required
        />
        <input
          type="email"
          placeholder="Email"
          value={newUser.email}
          onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
          required
        />
        <select
          value={newUser.role}
          onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
          required
        >
          <option value="">Select Role</option>
          <option value="admin">Admin</option>
          <option value="user">User</option>
        </select>
        <button type="submit">Create User</button>
      </form>

      <h2>Existing Users</h2>
      <ul>
        {users.map((user) => (
          <li key={user.id}>
            {editingUser && editingUser.id === user.id ? (
              <form onSubmit={handleUpdateUser}>
                <input
                  type="text"
                  value={editingUser.name}
                  onChange={(e) => setEditingUser({ ...editingUser, name: e.target.value })}
                  required
                />
                <input
                  type="email"
                  value={editingUser.email}
                  onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })}
                  required
                />
                <select
                  value={editingUser.role}
                  onChange={(e) => setEditingUser({ ...editingUser, role: e.target.value })}
                  required
                >
                  <option value="admin">Admin</option>
                  <option value="user">User</option>
                </select>
                <button type="submit">Save</button>
                <button type="button" onClick={() => setEditingUser(null)}>Cancel</button>
              </form>
            ) : (
              <>
                {user.name} ({user.email}) - {user.role}
                <button onClick={() => setEditingUser(user)}>Edit</button>
                <button onClick={() => handleDeleteUser(user.id)}>Delete</button>
              </>
            )}
          </li>
        ))}
      </ul>

      {message && <p>{message}</p>}
    </div>
  );
};

export default UserManagement;