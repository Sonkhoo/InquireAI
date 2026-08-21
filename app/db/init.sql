create extension if not exists "uuid-ossp";
--roles
create table if not exists roles (
    role_name varchar(50) unique not null primary key,
    created_at timestamp default current_timestamp
);
insert into roles (role_name) values ('user') on conflict do nothing;;
insert into roles (role_name) values ('hr') on conflict do nothing;;
insert into roles (role_name) values ('admin') on conflict do nothing;;
insert into roles (role_name) values ('engineer') on conflict do nothing;;
insert into roles (role_name) values ('marketer') on conflict do nothing;;


--users
create table if not exists users (
    id uuid primary key default uuid_generate_v4(),
    email varchar(255) unique not null,
    display_name varchar(255) not null,
    password varchar(255) not null,
    role varchar(50) references roles(role_name) default 'user',
    created_at timestamptz default current_timestamp
);
--workspaces
create table if not exists workspaces (
    id uuid primary key default uuid_generate_v4(),
    name varchar(255) not null,
    description text,
    created_at timestamptz default current_timestamp
);

--conversations
create table if not exists conversations (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid references users(id) on delete cascade,
    workspace_id uuid references workspaces(id) on delete cascade,
    title varchar(255) not null,
    created_at timestamptz default current_timestamp,
    updated_at timestamptz default current_timestamp
);

--messages
create table if not exists messages (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid references conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    metadata jsonb,
    created_at timestamptz default current_timestamp
);
create index if not exists idx_messages_conversation_id on messages(conversation_id, created_at);

insert into users (id, email, display_name, password)
values ('00000000-0000-0000-0000-000000000001', 'john@inquire.ai', 'John', 'dev-only')
on conflict (id) do nothing;

insert into workspaces (id, name)
values ('11111111-1111-1111-1111-111111111111', 'Demo Workspace')
on conflict (id) do nothing;